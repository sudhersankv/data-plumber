"""Planner demo: compare five GPU providers for an 8x H100, 6-hour job in US West.

The planner never reshapes provider data itself. Each provider payload goes through
Data Plumber (POST /v1/adapt), by default through the Pay.sh gateway, which charges
our service price of $0.02 per call.

    python -m demo.run_demo                 # through the Pay.sh sandbox gateway
    python -m demo.run_demo --mode direct   # straight to the API, no payment
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from clients.paid_http import post_json_paid, probe_price
from demo.providers import PROVIDERS, Provider, ProviderAPIError, adapt_request, call_primary_api, scrape_fallback

JOB = {
    "description": "8x H100 for 6 hours in US West, on-demand",
    "gpus": 8,
    "hours": 6,
    "region_keywords": ["west", "oregon", "california", "washington"],
}
OUTPUT = Path(__file__).resolve().parent / "output" / "last_run.json"


class Log:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def __call__(self, provider: str, message: str, kind: str = "info") -> None:
        self.events.append({"t": round(time.time(), 3), "provider": provider, "kind": kind, "message": message})
        print(f"  [{provider}] {message}", flush=True)


# ---------------------------------------------------------------- planning


def plan(rows: list[dict[str, Any]], job: dict[str, Any] = JOB) -> list[dict[str, Any]]:
    """Cost every normalized row for the job and mark which rows can be chosen."""
    planned = []
    for row in rows:
        data = row.get("data") or {}
        price = data.get("price_per_gpu_hour_usd")
        region = (data.get("region") or "").lower()
        warnings = row.get("warnings", [])
        entry = {
            "provider": data.get("provider") or row.get("provider_id"),
            "gpu": data.get("gpu"),
            "region": data.get("region"),
            "price_per_gpu_hour_usd": price,
            "price_type": data.get("price_type"),
            "job_cost_usd": round(price * job["gpus"] * job["hours"], 2) if isinstance(price, (int, float)) else None,
            "warnings": len(warnings),
            "eligible": True,
            "status": "on-demand quote" if data.get("price_type") == "on_demand" else "listed price (type not stated)",
        }
        if not row.get("valid"):
            entry.update(eligible=False, status="excluded: invalid row")
        elif price is None:
            entry.update(eligible=False, status="excluded: no price")
        elif data.get("price_type") == "starting_at" or any("lower bound" in w for w in warnings):
            entry.update(eligible=False, status="excluded: 'starting at' floor, not a quote")
        elif not any(k in region for k in job["region_keywords"]):
            entry.update(eligible=False, status="excluded: not US West")
        planned.append(entry)
    return planned


def choose(planned: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [p for p in planned if p["eligible"]]
    if not eligible:
        return None
    return min(eligible, key=lambda p: (p["job_cost_usd"], p["warnings"], str(p["provider"])))


# ---------------------------------------------------------------- calling Data Plumber


def call_direct(api_url: str, body: dict[str, Any], log: Log, pid: str) -> dict[str, Any]:
    response = httpx.post(f"{api_url}/v1/adapt", json=body, timeout=120)
    response.raise_for_status()
    return response.json()


def call_through_gateway(gateway_url: str, body: dict[str, Any], log: Log, pid: str) -> dict[str, Any]:
    url = f"{gateway_url}/v1/adapt"
    price = probe_price(url, body) or "see challenge"
    log(pid, f"402 Payment Required ({price} per call)", "payment")
    response = post_json_paid(
        url,
        body,
        on_retry=lambda _: log(
            pid, "Sandbox ledger rejected a duplicate transfer; retrying payment on a fresh blockhash", "payment"
        ),
    )
    log(pid, "Payment accepted; request forwarded to Data Plumber", "payment")
    return response


def fetch_row(provider: Provider, mode: str, args: argparse.Namespace, log: Log) -> dict[str, Any]:
    pid = provider.id
    log(pid, f"Calling {pid} pricing API")
    try:
        data = call_primary_api(provider)
        content_type = provider.content_type
        log(pid, f"API returned {content_type} in {pid}'s own format")
    except ProviderAPIError as exc:
        log(pid, f"API failed: {exc}", "error")
        data = scrape_fallback(provider)
        content_type = "text"
        log(pid, f"Fallback scrape obtained: {data!r}", "recovery")

    body = adapt_request(provider, content_type, data)
    log(pid, "Calling Data Plumber /v1/adapt")
    if mode == "gateway":
        response = call_through_gateway(args.gateway_url, body, log, pid)
    else:
        response = call_direct(args.api_url, body, log, pid)
    status = "valid" if response["valid"] else "INVALID"
    log(pid, f"Schema adapted: {status}, {len(response['warnings'])} warning(s)", "ok" if response["valid"] else "error")
    return {"provider_id": pid, "raw": data, "content_type": content_type, **response}


# ---------------------------------------------------------------- output


def print_report(rows: list[dict[str, Any]], planned: list[dict[str, Any]], pick: dict[str, Any] | None, calls: int) -> None:
    print("\nNormalized rows (GpuOffer schema):")
    for row in rows:
        print(f"  {row['provider_id']}: {json.dumps(row['data'])}")
        for w in row["warnings"]:
            print(f"      warning: {w}")

    print(f"\nJob: {JOB['description']}  ->  cost = price_per_gpu_hour_usd x {JOB['gpus']} x {JOB['hours']}\n")
    print(f"  {'provider':<9}{'$/GPU-hr':>10}{'job cost':>12}  {'region':<11} status")
    for p in sorted(planned, key=lambda p: (not p["eligible"], p["job_cost_usd"] or 1e18)):
        price = f"{p['price_per_gpu_hour_usd']:.4g}" if p["price_per_gpu_hour_usd"] is not None else "-"
        cost = f"${p['job_cost_usd']:,.2f}" if p["job_cost_usd"] is not None else "-"
        print(f"  {str(p['provider']):<9}{price:>10}{cost:>12}  {str(p['region']):<11} {p['status']}")

    if pick is None:
        print("\nPlan: no eligible provider.")
        return
    ties = [p for p in planned if p["eligible"] and p["job_cost_usd"] == pick["job_cost_usd"] and p is not pick]
    tie = f" (tied with {', '.join(str(t['provider']) for t in ties)}; picked the row with fewer warnings)" if ties else ""
    print(f"\nPlan: deploy on {pick['provider']} ({pick['gpu']}, {pick['region']}) for ${pick['job_cost_usd']:,.2f}{tie}.")
    print(f"Data Plumber calls: {calls} x $0.02 = ${calls * 0.02:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["gateway", "direct"], default="gateway")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:1402")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"Task: compare five GPU providers for {JOB['description']} and estimate cost.")
    print(f"Mode: {'Pay.sh sandbox gateway ' + args.gateway_url if args.mode == 'gateway' else 'direct ' + args.api_url}\n")
    log = Log()
    rows = []
    for provider in PROVIDERS:
        rows.append(fetch_row(provider, args.mode, args, log))
    log("planner", "All five rows share one schema; workflow resumed", "ok")

    planned = plan(rows)
    pick = choose(planned)
    print_report(rows, planned, pick, calls=len(rows))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"job": JOB, "mode": args.mode, "rows": rows, "plan": planned, "pick": pick, "log": log.events}, indent=2),
        encoding="utf-8",
    )
    print(f"\nRun saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
