"""Optional: the five demo providers through the real Fireworks model.

Runs only when FIREWORKS_API_KEY is set:  pytest -m live
"""

import pytest

from app.config import get_settings
from app.services.llm_client import FireworksClient
from app.services.pipeline import adapt
from demo.providers import PROVIDERS, adapt_request, load_payload

settings = get_settings()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not settings.fireworks_api_key, reason="FIREWORKS_API_KEY not set"),
]

EXPECTED_PRICE = {"A": 2.49, "B": 2.49, "C": 3.1, "D": 2.952, "E": 3.1}


@pytest.fixture(scope="module")
def client():
    return FireworksClient(settings.fireworks_api_key, settings.fireworks_model, settings.fireworks_base_url, 90)


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p.id)
def test_live_provider_normalizes(client, provider):
    body = adapt_request(provider, provider.content_type, load_payload(provider))
    result = adapt(provider.content_type, body["source"]["data"], body["target_schema"], provider.instructions, client)
    assert result.valid, result.warnings
    assert result.data["provider"] == provider.id
    assert result.data["price_per_gpu_hour_usd"] == pytest.approx(EXPECTED_PRICE[provider.id])
    if provider.id == "C":
        assert result.data["price_type"] == "starting_at"
        assert any("lower bound" in w for w in result.warnings)
    if provider.id == "B":
        assert result.data["vram_gb"] is None, "B's source does not state VRAM"
