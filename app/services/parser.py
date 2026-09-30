"""Step 1: turn the raw `source` into a Python value plus canonical text."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from app.models.internal import AdaptError, ParsedSource

CONTENT_TYPES = ("text", "json", "csv")

_HEADER_CELL = re.compile(r"^[A-Za-z_][A-Za-z0-9 _\-./()]*$")


def parse_source(content_type: str, data: Any) -> ParsedSource:
    if content_type not in CONTENT_TYPES:
        raise AdaptError(f"source.content_type must be one of {', '.join(CONTENT_TYPES)}")
    if content_type == "json":
        return _parse_json(data)
    if not isinstance(data, str):
        raise AdaptError(f"source.data must be a string when content_type is {content_type!r}")
    if not data.strip():
        raise AdaptError("source.data is empty")
    if content_type == "csv":
        return _parse_csv(data)
    return ParsedSource(content_type="text", value=data.strip(), text=data.strip())


def _parse_json(data: Any) -> ParsedSource:
    if isinstance(data, str):
        try:
            value = json.loads(data)
        except json.JSONDecodeError as exc:
            raise AdaptError(f"source.data is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}") from exc
    else:
        value = data
    if not isinstance(value, (dict, list)):
        raise AdaptError("JSON source must be an object or an array")
    if not value:
        raise AdaptError("source.data is empty")
    return ParsedSource(content_type="json", value=value, text=json.dumps(value, ensure_ascii=False))


def _parse_csv(data: str) -> ParsedSource:
    rows = [row for row in csv.reader(io.StringIO(data.strip())) if any(cell.strip() for cell in row)]
    if not rows:
        raise AdaptError("CSV source has no rows")
    width = max(len(r) for r in rows)
    if len(rows) > 1 and _looks_like_header(rows[0]):
        header = [h.strip() or f"col_{i + 1}" for i, h in enumerate(rows[0])]
        header += [f"col_{i + 1}" for i in range(len(header), width)]
        body = rows[1:]
    else:
        header = [f"col_{i + 1}" for i in range(width)]
        body = rows
    records = [{header[i]: (row[i].strip() if i < len(row) else "") for i in range(width)} for row in body]
    value: Any = records[0] if len(records) == 1 else records
    return ParsedSource(content_type="csv", value=value, text=data.strip())


def _looks_like_header(row: list[str]) -> bool:
    cells = [c.strip() for c in row]
    return all(c and _HEADER_CELL.match(c) and not re.search(r"\d", c) for c in cells)
