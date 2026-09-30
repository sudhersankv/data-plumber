"""Step 3: semantic field mapping with the model.

The model decides what the data means: which source value backs which target field, and
which formula turns it into the target unit. It does not produce the final object; code
recomputes and checks every value it proposes (see normalizer.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from app.models.internal import ParsedSource, Quantity
from app.services.expressions import CONSTANTS

MAX_SOURCE_CHARS = 20_000

MAPPING_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": ["string", "number", "integer", "boolean", "null", "object", "array"]},
                    "evidence": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "formula": {"type": "string"},
                    "missing": {"type": "boolean"},
                },
                "required": ["field", "value", "evidence", "interpretation", "formula", "missing"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fields", "warnings"],
}

SYSTEM_PROMPT = """You are the field-mapping step of Data Plumber, an API that adapts messy upstream data into a target JSON Schema for the next step of an automated workflow.

For every property of the target schema, return exactly one entry in "fields" with:
- field: the property name.
- value: the value for that property, or null.
- evidence: the exact text copied from the SOURCE or INSTRUCTIONS (never from the quantity list) that supports the value. Empty string if none.
- interpretation: one short sentence on how you read the evidence (e.g. "hourly price for the whole 8-GPU machine").
- formula: arithmetic for numeric values, written only with quantity ids (q1, q2, ...), the named constants, numbers, + - * / and parentheses. Use "q3" when the value is exactly a listed quantity. Use "" for non-numeric values.
- missing: true when the source and instructions do not state the value and it cannot be derived from them.

Rules:
1. Follow each property's "description" for meaning and units. When the source uses a different unit or basis, convert with a formula, e.g. "q2 / q1" to split a whole-machine price across its units, "q4 * SECONDS_PER_HOUR" to turn a per-second rate into per-hour.
2. Never do arithmetic only in your head. Every number that is not verbatim in the source must have a formula; code will recompute it.
3. Copy strings verbatim from the source unless the property's description asks for a different form. If it asks for a full name and the source uses a standard abbreviation, expand it and put the abbreviation in evidence. If the schema asks for a normalized label (e.g. "on_demand"), use it only when the source text actually says it (e.g. "on-demand"), put the label in value and that exact source text in evidence. A bare number or price is not evidence for a label.
4. Never invent facts. Do not fill a value from general knowledge, from the field name, or from what is typical. If it is not in the source or instructions, set missing=true, value=null, evidence="".
5. Preserve qualifiers. If a value is "starting at", "from", "up to", "about", or "~", say so in interpretation and in warnings, and use a matching label if the schema has one.
6. Add a warning for every real ambiguity (e.g. unclear whether a price is per machine or per unit).

Return only the JSON object."""


class MalformedMappingError(ValueError):
    pass


@dataclass
class FieldProposal:
    field: str
    value: Any
    evidence: str
    interpretation: str
    formula: str
    missing: bool


@dataclass
class Mapping:
    fields: dict[str, FieldProposal]
    warnings: list[str]
    unknown_fields: list[str]


def build_messages(
    source: ParsedSource,
    schema: dict[str, Any],
    quantities: list[Quantity],
    instructions: str | None,
) -> list[dict[str, str]]:
    text = source.text
    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS] + "\n...[truncated]"
    quantity_lines = "\n".join(q.describe() for q in quantities) or "(none found)"
    constants = ", ".join(f"{k}={v:g}" for k, v in CONSTANTS.items())
    user = (
        f"TARGET SCHEMA:\n{json.dumps(schema, indent=2)}\n\n"
        f"TARGET PROPERTIES (one entry each): {', '.join(schema.get('properties', {}))}\n\n"
        f"INSTRUCTIONS:\n{instructions.strip() if instructions and instructions.strip() else '(none)'}\n\n"
        f"SOURCE ({source.content_type}):\n{text}\n\n"
        f"QUANTITIES FOUND IN SOURCE (cite these ids in formulas):\n{quantity_lines}\n\n"
        f"CONSTANTS: {constants}\n\n"
        "Return the JSON mapping now."
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse_mapping(raw: str, properties: dict[str, Any]) -> Mapping:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    if not text:
        raise MalformedMappingError("model returned an empty response")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedMappingError(f"model output is not valid JSON ({exc.msg})") from exc
    errors = [e.message for e in Draft202012Validator(MAPPING_RESPONSE_SCHEMA).iter_errors(payload)]
    if errors:
        raise MalformedMappingError(f"model output does not match the mapping format: {errors[0]}")

    fields: dict[str, FieldProposal] = {}
    unknown: list[str] = []
    for entry in payload["fields"]:
        name = entry["field"]
        if name not in properties:
            unknown.append(name)
            continue
        fields[name] = FieldProposal(
            field=name,
            value=entry["value"],
            evidence=entry["evidence"],
            interpretation=entry["interpretation"],
            formula=entry["formula"].strip(),
            missing=entry["missing"],
        )
    return Mapping(fields=fields, warnings=[w for w in payload["warnings"] if w.strip()], unknown_fields=unknown)
