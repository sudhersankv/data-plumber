"""MCP wrapper exposing Data Plumber as a single tool, `adapt_data`.

    python -m mcp_server.server

Environment:
    DATA_PLUMBER_URL  base URL to call (default: the local Pay.sh gateway, http://127.0.0.1:1402)
    DATA_PLUMBER_PAY  sandbox (default) | mainnet | off. With `off`, the URL is called without
                      payment, which only works against the API itself, not the gateway.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer

from clients.paid_http import PaidCallError, post_json_paid

DEFAULT_URL = "http://127.0.0.1:1402"

server = MCPServer(
    name="data-plumber",
    instructions=(
        "Use adapt_data when an upstream payload (API response, fallback text, CSV row) is not in the "
        "shape you need. Pass the raw payload and a JSON Schema; you get back schema-valid data plus "
        "warnings about anything missing or ambiguous. Missing values come back as null, never guessed."
    ),
)


def _call(body: dict[str, Any]) -> dict[str, Any]:
    base = os.environ.get("DATA_PLUMBER_URL", DEFAULT_URL).rstrip("/")
    mode = os.environ.get("DATA_PLUMBER_PAY", "sandbox").lower()
    url = f"{base}/v1/adapt"
    if mode == "off":
        response = httpx.post(url, json=body, timeout=120)
        if response.status_code == 402:
            raise PaidCallError("this URL requires payment; set DATA_PLUMBER_PAY=sandbox")
        response.raise_for_status()
        return response.json()
    if mode not in ("sandbox", "mainnet"):
        raise PaidCallError(f"DATA_PLUMBER_PAY must be sandbox, mainnet or off, got {mode!r}")
    return post_json_paid(url, body, sandbox=mode == "sandbox")


@server.tool()
def adapt_data(
    content_type: Literal["text", "json", "csv"],
    data: Any,
    target_schema: dict[str, Any],
    instructions: str | None = None,
) -> dict[str, Any]:
    """Reshape a messy payload into the given JSON Schema. Costs $0.02 per call via Pay.sh.

    Args:
        content_type: "json" (object, array, or JSON string), "csv", or "text".
        data: the raw upstream payload.
        target_schema: JSON Schema (object, or array of objects) the result must match.
        instructions: optional hints, e.g. "The provider name is Acme."

    Returns {data, valid, warnings}.
    """
    body: dict[str, Any] = {"source": {"content_type": content_type, "data": data}, "target_schema": target_schema}
    if instructions:
        body["instructions"] = instructions
    return _call(body)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
