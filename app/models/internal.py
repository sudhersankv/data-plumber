from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class AdaptError(Exception):
    """A request the pipeline cannot process (bad input, bad schema). Maps to HTTP 422."""


class UpstreamLLMError(Exception):
    """The model provider could not be reached or rejected the call. Maps to HTTP 502."""


@dataclass
class ParsedSource:
    content_type: str
    value: Any
    """Parsed value: dict/list for JSON and CSV, str for text."""
    text: str
    """Canonical text of the source, used for prompting and grounding checks."""


@dataclass
class Quantity:
    id: str
    raw: str
    value: float | None
    path: str = ""
    kind: str = "number"
    """number | money | size | count | null"""
    unit: str | None = None
    per: str | None = None
    """Time unit the value is priced per, e.g. hour, second."""
    per_item: str | None = None
    """Item the value is priced per when stated, e.g. gpu in '$3.10 per GPU / hour'."""
    qualifiers: list[str] = field(default_factory=list)

    def describe(self) -> str:
        parts = [f"{self.id}", f"raw={self.raw!r}"]
        if self.path:
            parts.append(f"path={self.path}")
        parts.append(f"kind={self.kind}")
        parts.append(f"value={self.value!r}")
        if self.unit:
            parts.append(f"unit={self.unit}")
        if self.per:
            parts.append(f"per={self.per_item + '-' if self.per_item else ''}{self.per}")
        if self.qualifiers:
            parts.append(f"qualifiers={','.join(self.qualifiers)}")
        return "  ".join(parts)


@dataclass
class FieldTrace:
    field: str
    value: Any = None
    source_value: str | None = None
    interpretation: str | None = None
    derived: bool = False
    formula: str | None = None
    status: str = "missing"
    """copied | derived | interpreted | missing | rejected"""
    notes: list[str] = field(default_factory=list)


@dataclass
class AdaptResult:
    data: Any
    valid: bool
    warnings: list[str]
    trace: list[dict[str, Any]] = field(default_factory=list)
    repaired: bool = False

    def to_response(self, debug: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {"data": self.data, "valid": self.valid, "warnings": self.warnings}
        if debug:
            body["trace"] = self.trace
            body["repaired"] = self.repaired
        return body


def trace_dict(t: FieldTrace) -> dict[str, Any]:
    return asdict(t)
