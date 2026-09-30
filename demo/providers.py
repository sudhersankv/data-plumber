"""The five demo providers and a simulated upstream: each has a primary API, and C's API is down."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA_PATH = Path(__file__).resolve().parent / "gpu_offer.schema.json"


class ProviderAPIError(Exception):
    pass


@dataclass(frozen=True)
class Provider:
    id: str
    fixture: str
    content_type: str
    instructions: str | None
    api_down: bool = False
    """When true, the primary API fails and the planner falls back to the fixture (a scraped page)."""


PROVIDERS = [
    Provider("A", "provider_a.json", "json", "The provider name is A."),
    Provider("B", "provider_b.json", "json", "The provider name is B."),
    Provider(
        "C", "provider_c.txt", "text", "The provider name is C. This text was scraped from C's pricing page.", api_down=True
    ),
    Provider("D", "provider_d.json", "json", "The provider name is D."),
    Provider("E", "provider_e.csv", "csv", None),
]


def target_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_payload(provider: Provider) -> Any:
    raw = (FIXTURES / provider.fixture).read_text(encoding="utf-8")
    return json.loads(raw) if provider.content_type == "json" else raw.strip()


def call_primary_api(provider: Provider) -> Any:
    """Stand-in for each provider's pricing API."""
    if provider.api_down:
        raise ProviderAPIError(f"{provider.id} pricing API returned HTTP 503")
    return load_payload(provider)


def scrape_fallback(provider: Provider) -> str:
    """Stand-in for the fallback scrape of the provider's public pricing page."""
    return (FIXTURES / provider.fixture).read_text(encoding="utf-8").strip()


def adapt_request(provider: Provider, content_type: str, data: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source": {"content_type": content_type, "data": data},
        "target_schema": target_schema(),
    }
    if provider.instructions:
        body["instructions"] = provider.instructions
    return body
