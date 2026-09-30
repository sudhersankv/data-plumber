"""Pay.sh gateway acceptance. Needs the API and a sandbox gateway running:

uvicorn app.main:app --host 127.0.0.1 --port 8000
pay --sandbox gate api pay/paywall.yml --bind 127.0.0.1:1402
DP_GATEWAY_URL=http://127.0.0.1:1402 pytest -m gateway
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from clients.paid_http import challenge_price

GATEWAY = os.getenv("DP_GATEWAY_URL", "").rstrip("/")
PAY = shutil.which("pay")
REQUEST = Path(__file__).resolve().parent.parent / "examples" / "acme_request.json"

pytestmark = [
    pytest.mark.gateway,
    pytest.mark.skipif(not GATEWAY, reason="DP_GATEWAY_URL not set"),
]


def body() -> dict:
    return json.loads(REQUEST.read_text(encoding="utf-8"))


def test_unpaid_adapt_gets_402_with_our_price():
    response = httpx.post(f"{GATEWAY}/v1/adapt", json=body(), timeout=30)
    assert response.status_code == 402
    assert challenge_price(response.headers.get("www-authenticate")) == "$0.02"


def test_forged_payment_does_not_pass_through():
    response = httpx.post(
        f"{GATEWAY}/v1/adapt",
        json=body(),
        headers={"X-PAYMENT": "forged", "Authorization": "Payment forged"},
        timeout=30,
    )
    assert response.status_code in (400, 401, 402)


def test_health_is_free():
    assert httpx.get(f"{GATEWAY}/v1/health", timeout=10).json() == {"status": "ok"}


@pytest.mark.skipif(PAY is None, reason="pay CLI not on PATH")
def test_paid_sandbox_call_returns_adapted_data():
    marker = "__STATUS__:"
    result = subprocess.run(
        [PAY, "--sandbox", "curl", "-s", "-X", "POST", f"{GATEWAY}/v1/adapt",
         "-H", "Content-Type:application/json", "--data-binary", f"@{REQUEST}",
         "-w", marker + "%{http_code}"],
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )  # fmt: skip
    text, _, status = result.stdout.rstrip().rpartition(marker)
    assert status == "200", result.stdout + result.stderr
    payload = json.loads(text)
    assert payload["valid"] is True
    assert payload["data"]["company_name"] == "Acme"
    assert payload["data"]["funding_usd"] == 12_000_000
