"""Live demo console: the planner and a playground for /v1/adapt, streamed to a browser.

    python -m demo.console            # then open http://127.0.0.1:8700

The console plays the agent. It pays through the Pay.sh gateway with the `pay` CLI (sandbox),
or calls the API directly, and streams every step to the page as server-sent events.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from clients.paid_http import PaidCallError, challenge_price, post_paid
from demo.providers import PROVIDERS, load_payload, target_schema
from demo.run_demo import JOB, OUTPUT, Log, choose, fetch_row, plan, save_run

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "ui" / "console.html"
PRESETS = Path(__file__).resolve().parent / "presets.json"
GATEWAY_LOG = OUTPUT.parent / "gateway.log"


@dataclasses.dataclass
class Config:
    api_url: str = "http://127.0.0.1:8000"
    gateway_url: str = "http://127.0.0.1:1402"


config = Config()
app = FastAPI(title="Data Plumber console", docs_url=None, redoc_url=None)
_gateway_process: subprocess.Popen | None = None


class PlanRequest(BaseModel):
    mode: str = Field("gateway", pattern="^(gateway|direct)$")
    down: list[str] = ["C"]
    gpus: int = Field(JOB["gpus"], ge=1, le=1024)
    hours: float = Field(JOB["hours"], gt=0, le=10_000)


class ReplanRequest(BaseModel):
    rows: list[dict[str, Any]]
    gpus: int = Field(JOB["gpus"], ge=1, le=1024)
    hours: float = Field(JOB["hours"], gt=0, le=10_000)


class PlaygroundRequest(BaseModel):
    mode: str = Field("gateway", pattern="^(gateway|direct)$")
    debug: bool = True
    body: Any


def _job(gpus: int, hours: float) -> dict[str, Any]:
    hours_label = f"{hours:g}"
    return {**JOB, "gpus": gpus, "hours": hours, "description": f"{gpus}x H100 for {hours_label} hours in US West, on-demand"}


def _stream(work: Callable[[Callable[[dict[str, Any]], None]], None]) -> StreamingResponse:
    """Run `work` in a thread; every event it emits is sent to the browser as one SSE message."""
    events: queue.Queue = queue.Queue()
    done = object()

    def run() -> None:
        try:
            work(events.put)
        except Exception as exc:  # surfaced to the page instead of a broken stream
            events.put({"type": "fatal", "message": str(exc)})
        finally:
            events.put(done)

    threading.Thread(target=run, daemon=True).start()

    def body() -> Iterator[str]:
        while True:
            item = events.get()
            if item is done:
                yield "data: " + json.dumps({"type": "end"}) + "\n\n"
                return
            yield "data: " + json.dumps(item, default=str) + "\n\n"

    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- pages and metadata


@app.get("/")
def page() -> FileResponse:
    return FileResponse(PAGE, headers={"Cache-Control": "no-store"})


def _probe(url: str) -> dict[str, Any] | None:
    try:
        response = httpx.get(url, timeout=1.5)
        return response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


@app.get("/api/status")
def status() -> dict[str, Any]:
    api = _probe(f"{config.api_url}/v1/health")
    gateway = _probe(f"{config.gateway_url}/v1/health")
    return {
        "api": api is not None,
        "gateway": gateway is not None,
        "model": bool(api and api.get("model_configured")),
        "pay_cli": shutil.which("pay") is not None,
        "api_url": config.api_url,
        "gateway_url": config.gateway_url,
    }


@app.post("/api/gateway/start")
def start_gateway() -> dict[str, Any]:
    """Start the sandbox gateway on localhost if it is not running (it exits on its own after a few minutes)."""
    global _gateway_process
    if _probe(f"{config.gateway_url}/v1/health") is not None:
        return {"gateway": True, "started": False}
    pay = shutil.which("pay")
    if not pay:
        raise HTTPException(status_code=400, detail="the `pay` CLI is not on PATH")
    bind = config.gateway_url.split("://", 1)[-1].rstrip("/")
    GATEWAY_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_file = GATEWAY_LOG.open("ab")
    _gateway_process = subprocess.Popen(
        [pay, "--sandbox", "gate", "api", str(ROOT / "pay" / "paywall.yml"), "--bind", bind],
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(40):
        time.sleep(0.25)
        if _probe(f"{config.gateway_url}/v1/health") is not None:
            return {"gateway": True, "started": True}
    raise HTTPException(status_code=504, detail=f"gateway did not come up; see {GATEWAY_LOG}")


@app.get("/api/providers")
def providers() -> dict[str, Any]:
    return {
        "job": JOB,
        "schema": target_schema(),
        "providers": [
            {"id": p.id, "content_type": p.content_type, "raw": load_payload(p), "api_down": p.api_down} for p in PROVIDERS
        ],
    }


@app.get("/api/presets")
def presets() -> list[dict[str, Any]]:
    items = json.loads(PRESETS.read_text(encoding="utf-8"))
    gpu_schema = target_schema()
    for item in items:
        if item["request"].get("target_schema") == {"$ref_gpu_schema": True}:
            item["request"]["target_schema"] = gpu_schema
    return items


@app.get("/api/last-run")
def last_run() -> JSONResponse:
    if not OUTPUT.exists():
        raise HTTPException(status_code=404, detail="no saved run yet; run the planner once")
    return JSONResponse(json.loads(OUTPUT.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- planner


@app.post("/api/plan")
def run_plan(request: PlanRequest) -> StreamingResponse:
    job = _job(request.gpus, request.hours)
    down = {d.upper() for d in request.down}

    def work(emit: Callable[[dict[str, Any]], None]) -> None:
        log = Log(sink=lambda e: emit({"type": "log", **e}), echo=False)
        emit({"type": "start", "mode": request.mode, "job": job, "providers": [p.id for p in PROVIDERS]})

        def one(provider) -> dict[str, Any]:
            provider = dataclasses.replace(provider, api_down=provider.id in down)
            try:
                row = fetch_row(provider, request.mode, log, api_url=config.api_url, gateway_url=config.gateway_url)
            except (httpx.HTTPError, PaidCallError, RuntimeError, ValueError) as exc:
                log(provider.id, f"Data Plumber call failed: {exc}", "error", stage="error")
                row = {
                    "provider_id": provider.id,
                    "raw": None,
                    "content_type": None,
                    "data": None,
                    "valid": False,
                    "warnings": [str(exc)],
                }
            emit({"type": "row", "row": row})
            return row

        # Paid calls go one at a time: parallel sandbox transfers from one wallet collide.
        if request.mode == "direct":
            with ThreadPoolExecutor(max_workers=len(PROVIDERS)) as pool:
                rows = list(pool.map(one, PROVIDERS))
        else:
            rows = [one(p) for p in PROVIDERS]

        log("planner", "All five rows share one schema; workflow resumed", "ok", stage="planned")
        planned = plan(rows, job)
        pick = choose(planned)
        paid_calls = sum(1 for e in log.events if e.get("stage") == "paid")
        emit({"type": "plan", "plan": planned, "pick": pick, "job": job, "paid_calls": paid_calls})
        save_run(OUTPUT, job, request.mode, rows, planned, pick, log)

    return _stream(work)


@app.post("/api/replan")
def replan(request: ReplanRequest) -> dict[str, Any]:
    job = _job(request.gpus, request.hours)
    planned = plan(request.rows, job)
    return {"plan": planned, "pick": choose(planned), "job": job}


# ---------------------------------------------------------------- playground


def _parse(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text


@app.post("/api/adapt")
def playground(request: PlaygroundRequest) -> StreamingResponse:
    query = "?debug=true" if request.debug else ""

    def work(emit: Callable[[dict[str, Any]], None]) -> None:
        started = time.perf_counter()

        def elapsed() -> int:
            return round((time.perf_counter() - started) * 1000)

        emit({"type": "step", "step": "request", "mode": request.mode})
        if request.mode == "direct":
            response = httpx.post(f"{config.api_url}/v1/adapt{query}", json=request.body, timeout=180)
            emit(
                {
                    "type": "step",
                    "step": "response",
                    "status": response.status_code,
                    "ms": elapsed(),
                    "body": _parse(response.text),
                }
            )
            return

        url = f"{config.gateway_url}/v1/adapt{query}"
        probe = httpx.post(url, json=request.body, timeout=30)
        if probe.status_code != 402:
            emit({"type": "step", "step": "response", "status": probe.status_code, "ms": elapsed(), "body": _parse(probe.text)})
            return
        price = challenge_price(probe.headers.get("www-authenticate"))
        emit({"type": "step", "step": "challenge", "status": 402, "price": price, "ms": elapsed()})
        emit({"type": "step", "step": "paying", "ms": elapsed()})
        status_code, text = post_paid(
            url, request.body, on_retry=lambda n: emit({"type": "step", "step": "retry", "attempt": n, "ms": elapsed()})
        )
        emit({"type": "step", "step": "paid", "ms": elapsed()})
        emit({"type": "step", "step": "response", "status": status_code, "ms": elapsed(), "body": _parse(text)})

    return _stream(work)


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8700)
    parser.add_argument("--api-url", default=config.api_url)
    parser.add_argument("--gateway-url", default=config.gateway_url)
    args = parser.parse_args(argv)
    config.api_url = args.api_url.rstrip("/")
    config.gateway_url = args.gateway_url.rstrip("/")
    print(f"Data Plumber console on http://127.0.0.1:{args.port}  (API {config.api_url}, gateway {config.gateway_url})")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
