"""Payment lives entirely in the Pay.sh gateway. The adaptation service must not know about it."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
PAYMENT_TERMS = re.compile(r"\b402\b|payment|x-payment|www-authenticate|solana|usdc|wallet|pay\.sh", re.IGNORECASE)


def test_app_contains_no_payment_logic():
    offenders = [
        f"{path.relative_to(APP.parent)}:{n}: {line.strip()}"
        for path in APP.rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if PAYMENT_TERMS.search(line)
    ]
    assert offenders == []
