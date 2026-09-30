import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_llm_client
from app.main import app
from tests.helpers import FakeLLM, entry, mapping

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "count": {"type": ["integer", "null"]}},
    "required": ["name"],
}


@pytest.fixture
def client_with(request):
    def make(*responses):
        llm = FakeLLM(*responses)
        app.dependency_overrides[get_llm_client] = lambda: llm
        return TestClient(app), llm

    yield make
    app.dependency_overrides.clear()


def test_health(client_with):
    client, _ = client_with()
    assert client.get("/v1/health").json() == {"status": "ok"}


def test_adapt_returns_public_contract(client_with):
    client, _ = client_with(mapping(entry("name", "Acme", evidence="Acme"), entry("count", 3, formula="q1")))
    response = client.post(
        "/v1/adapt",
        json={"source": {"content_type": "json", "data": {"n": "Acme", "c": "3"}}, "target_schema": SCHEMA},
    )
    assert response.status_code == 200
    assert response.json() == {"data": {"name": "Acme", "count": 3}, "valid": True, "warnings": []}


def test_debug_includes_trace(client_with):
    client, _ = client_with(mapping(entry("name", "Acme", evidence="Acme"), entry("count", None, missing=True)))
    response = client.post(
        "/v1/adapt?debug=true",
        json={"source": {"content_type": "text", "data": "Acme"}, "target_schema": SCHEMA},
    )
    body = response.json()
    assert body["trace"][0]["field"] == "name"
    assert body["trace"][0]["status"] == "copied"
    assert "repaired" in body


@pytest.mark.parametrize(
    "payload, fragment",
    [
        ({"source": {"content_type": "json", "data": "{bad"}, "target_schema": SCHEMA}, "not valid JSON"),
        ({"source": {"content_type": "text", "data": "x"}, "target_schema": {"type": 5}}, "not a valid JSON Schema"),
        ({"source": {"content_type": "csv", "data": {"a": 1}}, "target_schema": SCHEMA}, "must be a string"),
        ({"source": {"content_type": "text", "data": "x"}, "target_schema": {"type": "string"}}, "must describe an object"),
    ],
)
def test_bad_input_is_422_with_a_reason(client_with, payload, fragment):
    client, llm = client_with()
    response = client.post("/v1/adapt", json=payload)
    assert response.status_code == 422
    assert fragment in response.json()["detail"]
    assert llm.calls == [], "bad input must be rejected before any model call"


@pytest.mark.parametrize(
    "payload",
    [
        {"source": {"content_type": "pdf", "data": "x"}, "target_schema": SCHEMA},
        {"source": {"content_type": "text"}, "target_schema": SCHEMA},
        {"target_schema": SCHEMA},
        {"source": {"content_type": "text", "data": "x"}, "target_schema": SCHEMA, "extra": 1},
    ],
)
def test_malformed_request_shape_is_422(client_with, payload):
    client, _ = client_with()
    assert client.post("/v1/adapt", json=payload).status_code == 422


def test_missing_api_key_is_503(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "")
    app.dependency_overrides.clear()
    response = TestClient(app).post("/v1/adapt", json={"source": {"content_type": "text", "data": "x"}, "target_schema": SCHEMA})
    assert response.status_code == 503
