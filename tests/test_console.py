import json

import pytest
from fastapi.testclient import TestClient

import demo.console as console
from demo.providers import target_schema

PRICES = {"A": 2.49, "B": 2.49, "C": 3.1, "D": 2.952, "E": 3.1}


def fake_row(provider, mode, log, api_url, gateway_url):
    log(provider.id, f"Calling {provider.id} pricing API", stage="calling")
    if provider.api_down:
        log(provider.id, "API failed: 503", "error", stage="api_down")
    log(provider.id, "Schema adapted: valid, 0 warning(s)", "ok", stage="adapted")
    data = {
        "provider": provider.id,
        "gpu": "H100",
        "price_per_gpu_hour_usd": PRICES[provider.id],
        "region": "us-west",
        "price_type": "starting_at" if provider.id == "C" else "on_demand",
    }
    return {"provider_id": provider.id, "raw": None, "content_type": "json", "data": data, "valid": True, "warnings": []}


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(console, "fetch_row", fake_row)
    monkeypatch.setattr(console, "OUTPUT", tmp_path / "last_run.json")
    return TestClient(console.app)


def test_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Data Plumber" in response.text


def test_presets_are_complete_requests(client):
    presets = client.get("/api/presets").json()
    assert len({p["id"] for p in presets}) == len(presets)
    for p in presets:
        assert {"id", "group", "title", "expect", "request"} <= p.keys()
        assert "source" in p["request"] and "target_schema" in p["request"]
    gpu = next(p for p in presets if p["id"] == "gpu-c")
    assert gpu["request"]["target_schema"] == target_schema()


def test_plan_streams_rows_and_a_pick(client):
    response = client.post("/api/plan", json={"mode": "direct", "down": ["C", "D"], "gpus": 8, "hours": 6})
    stream = events(response)
    kinds = [e["type"] for e in stream]
    assert kinds[0] == "start" and kinds[-1] == "end"
    assert sum(k == "row" for k in kinds) == 5
    downs = {e["provider"] for e in stream if e.get("stage") == "api_down"}
    assert downs == {"C", "D"}
    plan = next(e for e in stream if e["type"] == "plan")
    assert plan["pick"]["provider"] == "A"
    assert plan["pick"]["job_cost_usd"] == 119.52
    assert plan["paid_calls"] == 0
    assert console.OUTPUT.exists()


def test_replan_uses_the_new_job(client):
    rows = [fake_row(p, "direct", console.Log(echo=False), "", "") for p in console.PROVIDERS]
    body = client.post("/api/replan", json={"rows": rows, "gpus": 4, "hours": 10}).json()
    assert body["pick"]["job_cost_usd"] == round(2.49 * 4 * 10, 2)
    assert body["job"]["gpus"] == 4


def test_invalid_mode_is_rejected(client):
    assert client.post("/api/plan", json={"mode": "mainnet"}).status_code == 422


def test_playground_direct_passes_the_api_response_through(client, monkeypatch):
    class Response:
        status_code = 422
        text = '{"detail": "source is not valid JSON"}'

    calls = []
    monkeypatch.setattr(console.httpx, "post", lambda url, **kw: calls.append(url) or Response())
    stream = events(client.post("/api/adapt", json={"mode": "direct", "debug": True, "body": {"x": 1}}))
    final = next(e for e in stream if e.get("step") == "response")
    assert final["status"] == 422
    assert final["body"] == {"detail": "source is not valid JSON"}
    assert calls[0].endswith("/v1/adapt?debug=true")
