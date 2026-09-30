"""Model access. The pipeline depends only on `LLMClient`, so tests can inject a fake."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.models.internal import UpstreamLLMError


class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str: ...


class FireworksClient:
    """Fireworks chat completions with JSON-schema constrained output (OpenAI-compatible API)."""

    def __init__(self, api_key: str, model: str, base_url: str, timeout_s: float = 60.0) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._timeout = timeout_s

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "field_mapping", "schema": response_schema},
            },
        }
        try:
            response = httpx.post(self._url, headers=self._headers, json=body, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise UpstreamLLMError(f"model request failed: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise UpstreamLLMError(f"model provider returned HTTP {response.status_code}: {response.text[:300]}")
        try:
            content = response.json()["choices"][0]["message"].get("content")
        except (ValueError, KeyError, IndexError) as exc:
            raise UpstreamLLMError("model provider returned an unexpected response body") from exc
        return content or ""
