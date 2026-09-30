from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.services.annotator import annotate
from app.services.parser import parse_source

Response = str | Callable[[list[dict[str, str]]], str]


class FakeLLM:
    """Returns scripted responses in order and records every prompt it receives."""

    def __init__(self, *responses: Response) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeLLM received more calls than scripted responses")
        response = self.responses.pop(0)
        return response(messages) if callable(response) else response


def entry(
    field: str,
    value: Any = None,
    *,
    evidence: str = "",
    interpretation: str = "",
    formula: str = "",
    missing: bool = False,
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "interpretation": interpretation,
        "formula": formula,
        "missing": missing,
    }


def mapping(*entries: dict[str, Any], warnings: list[str] | None = None) -> str:
    return json.dumps({"fields": list(entries), "warnings": warnings or []})


def qid(content_type: str, data: Any, raw: str, kind: str | None = None, instructions: str | None = None) -> str:
    """Find the annotator id of the quantity whose raw text contains `raw`."""
    for q in annotate(parse_source(content_type, data), instructions):
        if raw in q.raw and (kind is None or q.kind == kind):
            return q.id
    raise AssertionError(f"no quantity matching {raw!r} (kind={kind})")
