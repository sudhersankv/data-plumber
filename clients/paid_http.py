"""Client side of the Pay.sh flow: POST JSON to a 402-gated URL and let the `pay` CLI pay for it.

Used by the demo planner and the MCP wrapper. The Data Plumber API itself never imports this.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

STATUS_MARKER = "__DP_HTTP_STATUS__:"
# The sandbox ledger reuses a recent blockhash for a while, so two identical $0.02 transfers
# from the same wallet can collide as "already processed". A new blockhash fixes it.
PAYMENT_ATTEMPTS = 4
PAYMENT_RETRY_DELAY_S = 3


class PaidCallError(RuntimeError):
    pass


def challenge_price(www_authenticate: str | None) -> str | None:
    """Read the amount from a Pay.sh MPP challenge header, for display only."""
    if not www_authenticate or 'request="' not in www_authenticate:
        return None
    try:
        encoded = www_authenticate.split('request="', 1)[1].split('"', 1)[0]
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        decimals = int(payload.get("methodDetails", {}).get("decimals", 6))
        return f"${int(payload['amount']) / 10**decimals:.2f}"
    except (ValueError, KeyError, TypeError):
        return None


def probe_price(url: str, body: dict[str, Any]) -> str | None:
    """Send the request unpaid. The gateway must answer 402; returns the advertised price."""
    response = httpx.post(url, json=body, timeout=30)
    if response.status_code != 402:
        raise PaidCallError(f"expected 402 from the gateway without payment, got {response.status_code}")
    return challenge_price(response.headers.get("www-authenticate"))


def post_json_paid(
    url: str,
    body: dict[str, Any],
    sandbox: bool = True,
    on_retry: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    pay = shutil.which("pay")
    if not pay:
        raise PaidCallError("the `pay` CLI is not on PATH")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(body, f)
        body_path = f.name
    network = ["--sandbox"] if sandbox else []
    command = [
        pay, *network, "curl", "-s", "-X", "POST", url,
        "-H", "Content-Type:application/json",
        "--data-binary", f"@{body_path}",
        "-w", STATUS_MARKER + "%{http_code}",
    ]  # fmt: skip
    try:
        for attempt in range(1, PAYMENT_ATTEMPTS + 1):
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=180)
            out = result.stdout.rstrip()
            body_text, _, status = out.rpartition(STATUS_MARKER)
            if result.returncode == 0 and status == "200":
                return json.loads(body_text)
            detail = result.stderr.strip() or out[:300]
            if "already been processed" not in out + detail or attempt == PAYMENT_ATTEMPTS:
                raise PaidCallError(f"paid call failed (exit {result.returncode}, status {status!r}): {detail}")
            if on_retry:
                on_retry(attempt)
            time.sleep(PAYMENT_RETRY_DELAY_S)
    finally:
        Path(body_path).unlink(missing_ok=True)
    raise PaidCallError("paid call failed")
