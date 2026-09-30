"""Steps 4-5: deterministic normalization and recomputation of the model's proposal.

The model decides what the data means. This module decides what is actually returned:
- numeric values come from formulas over parsed quantities, recomputed here;
- every value must be grounded in the source or instructions, or it becomes null;
- values are coerced to the types the target schema allows;
- qualifiers such as "starting at" or "~" become warnings.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.models.internal import FieldTrace, Quantity
from app.services.annotator import NULL_SENTINELS
from app.services.expressions import FormulaError, evaluate, referenced_ids
from app.services.llm_mapper import FieldProposal, Mapping

_QUALIFIER_TEXT = {
    "floor": "is a lower bound ('{raw}'), not a firm value",
    "ceiling": "is an upper bound ('{raw}'), not a firm value",
    "approximate": "is approximate ('{raw}')",
    "estimate": "is an estimate ('{raw}')",
}
_NUMERIC = re.compile(r"^\s*[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.\d+)?\s*$")


@dataclass
class NormalizedObject:
    data: dict[str, Any]
    traces: list[FieldTrace]
    warnings: list[str]
    reported_missing: set[str] = field(default_factory=set)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def allowed_types(prop: dict[str, Any]) -> set[str]:
    declared = prop.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return set(declared)
    types: set[str] = set()
    for key in ("anyOf", "oneOf"):
        for option in prop.get(key, []):
            if isinstance(option, dict):
                types |= allowed_types(option)
    return types


def _nullable(types: set[str]) -> bool:
    return not types or "null" in types


def _clean_number(value: float) -> float | int:
    value = float(f"{value:.12g}")
    return int(value) if value.is_integer() else value


def coerce(value: Any, types: set[str]) -> tuple[Any, str | None]:
    """Coerce a value toward the schema's types. Returns (value, note)."""
    if value is None:
        return None, None
    if isinstance(value, str) and value.strip().lower() in NULL_SENTINELS:
        if value.strip() or "string" not in types:
            return None, f"source value {value!r} treated as null"
    if not types:
        return value, None
    if isinstance(value, bool):
        return value, None
    if isinstance(value, (int, float)):
        if "integer" in types and "number" not in types:
            if float(value).is_integer():
                return int(value), None
            return value, None
        if "number" in types or "integer" in types:
            return _clean_number(float(value)), None
        if "string" in types:
            return str(_clean_number(float(value))), "number converted to string"
        return value, None
    if isinstance(value, str):
        stripped = value.strip()
        if ("number" in types or "integer" in types) and "string" not in types and _NUMERIC.match(stripped) and stripped:
            number = float(stripped.replace(",", ""))
            if "integer" in types and "number" not in types and number.is_integer():
                return int(number), "numeric string converted to integer"
            return _clean_number(number), "numeric string converted to number"
        if "boolean" in types and "string" not in types and stripped.lower() in {"true", "yes", "false", "no"}:
            return stripped.lower() in {"true", "yes"}, "string converted to boolean"
    return value, None


def snap_to_enum(value: Any, enum: Any) -> tuple[Any, str | None]:
    """Map 'on-demand' / 'On Demand' onto an enum member 'on_demand' when they differ only in case and punctuation."""
    if not isinstance(value, str) or not isinstance(enum, list) or value in enum:
        return value, None
    matches = [m for m in enum if isinstance(m, str) and _norm(m) == _norm(value)]
    if len(matches) == 1:
        return matches[0], f"{value!r} matched enum value {matches[0]!r}"
    return value, None


class _Grounding:
    def __init__(self, source_text: str, instructions: str | None, quantities: list[Quantity]) -> None:
        self.corpus = _norm(source_text + " " + (instructions or ""))
        self.quantities = {q.id: q for q in quantities}
        self.numbers = [q for q in quantities if q.value is not None]

    def text_grounded(self, text: str) -> bool:
        needle = _norm(text)
        return bool(needle) and needle in self.corpus

    def matching_quantity(self, value: float) -> Quantity | None:
        for q in self.numbers:
            if math.isclose(q.value, value, rel_tol=1e-9, abs_tol=1e-12):
                return q
        return None


def _qualifier_warnings(name: str, used: list[Quantity]) -> list[str]:
    out = []
    for q in used:
        for qualifier in q.qualifiers:
            template = _QUALIFIER_TEXT.get(qualifier)
            if template:
                out.append(f"{name}: source value " + template.format(raw=q.raw))
    return out


def _normalize_field(
    name: str,
    prop: dict[str, Any],
    proposal: FieldProposal | None,
    ground: _Grounding,
) -> tuple[Any, FieldTrace, list[str]]:
    types = allowed_types(prop)
    trace = FieldTrace(field=name)
    warnings: list[str] = []

    if proposal is None or proposal.missing or (proposal.value is None and not proposal.formula):
        trace.status = "missing"
        if proposal is not None:
            trace.interpretation = proposal.interpretation or None
        return None, trace, warnings

    trace.source_value = proposal.evidence or None
    trace.interpretation = proposal.interpretation or None
    value: Any = proposal.value
    used: list[Quantity] = []

    if proposal.formula:
        ids = referenced_ids(proposal.formula)
        used = [ground.quantities[i] for i in ids if i in ground.quantities]
        try:
            computed = evaluate(proposal.formula, ground.quantities)
        except FormulaError as exc:
            trace.status = "rejected"
            trace.notes.append(str(exc))
            warnings.append(f"{name}: could not recompute the proposed value ({exc}); set to null")
            return None, trace, warnings
        if not _depends_on_source(proposal.formula, ids, ground.quantities, computed):
            return _reject(
                name, proposal.value, trace, warnings, f"formula {proposal.formula!r} does not depend on any source value"
            )
        computed = _clean_number(computed)
        single_copy = len(ids) == 1 and proposal.formula.strip() == ids[0]
        trace.formula = None if single_copy else _readable_formula(proposal.formula, ground.quantities)
        trace.derived = not single_copy
        trace.status = "copied" if single_copy else "derived"
        if trace.source_value is None and used:
            trace.source_value = ", ".join(q.raw for q in used)
        if isinstance(proposal.value, (int, float)) and not isinstance(proposal.value, bool):
            if not math.isclose(float(proposal.value), float(computed), rel_tol=1e-6, abs_tol=1e-9):
                trace.notes.append(f"model proposed {proposal.value}, recomputed {computed}")
                warnings.append(
                    f"{name}: model's value {proposal.value} did not match its own formula; using recomputed {computed}"
                )
        value = computed
    elif isinstance(value, bool):
        if not ground.text_grounded(proposal.evidence):
            return _reject(name, value, trace, warnings, "no supporting text in the source")
        trace.status = "interpreted"
    elif isinstance(value, (int, float)):
        match = ground.matching_quantity(float(value))
        if match is None:
            return _reject(name, value, trace, warnings, "number does not appear in the source and has no formula")
        used = [match]
        trace.status = "copied"
        trace.source_value = trace.source_value or match.raw
    elif isinstance(value, str):
        if value.strip().lower() in NULL_SENTINELS:
            trace.status = "missing"
            trace.notes.append(f"source value {value!r} treated as null")
            return None, trace, warnings
        label, _ = snap_to_enum(value, prop.get("enum"))
        if isinstance(prop.get("enum"), list) and not ground.text_grounded(label):
            return _reject(name, value, trace, warnings, "label is not stated in the source")
        if ground.text_grounded(value):
            trace.status = "copied"
            if not ground.text_grounded(proposal.evidence):
                trace.source_value = value
        elif ground.text_grounded(proposal.evidence):
            trace.status = "interpreted"
            warnings.append(f"{name}: interpreted source text {proposal.evidence!r} as {value!r}")
        else:
            return _reject(name, value, trace, warnings, "text does not appear in the source")
    else:
        if not ground.text_grounded(proposal.evidence):
            return _reject(name, value, trace, warnings, "no supporting text in the source")
        trace.status = "interpreted"

    if used and not ground.text_grounded(proposal.evidence):
        trace.source_value = ", ".join(dict.fromkeys(q.raw for q in used))
    value, note = coerce(value, types)
    if note:
        trace.notes.append(note)
    value, note = snap_to_enum(value, prop.get("enum"))
    if note:
        trace.notes.append(note)
    trace.value = value
    warnings.extend(_qualifier_warnings(name, used))
    return value, trace, warnings


def _depends_on_source(formula: str, ids: list[str], quantities: dict[str, Quantity], result: float) -> bool:
    """A formula must change when a source value changes; '1' or 'q1 / q1' only launder a guess."""
    for qid in ids:
        original = quantities.get(qid)
        if original is None or original.value is None:
            continue
        nudged = dict(quantities)
        nudged[qid] = replace(original, value=original.value * 1.37 + 0.11)
        try:
            if not math.isclose(evaluate(formula, nudged), result, rel_tol=1e-12, abs_tol=1e-12):
                return True
        except FormulaError:
            return True
    return False


def _reject(name: str, value: Any, trace: FieldTrace, warnings: list[str], reason: str) -> tuple[Any, FieldTrace, list[str]]:
    trace.status = "rejected"
    trace.notes.append(f"model proposed {value!r}: {reason}")
    warnings.append(f"{name}: dropped model value {value!r} because the {reason}; set to null")
    return None, trace, warnings


def _readable_formula(formula: str, quantities: dict[str, Quantity]) -> str:
    def sub(m: re.Match[str]) -> str:
        q = quantities.get(m.group(0))
        return f"{q.value:g}" if q and q.value is not None else m.group(0)

    return re.sub(r"\bq\d+\b", sub, formula)


def normalize(
    mapping: Mapping,
    schema: dict[str, Any],
    quantities: list[Quantity],
    source_text: str,
    instructions: str | None,
) -> NormalizedObject:
    properties: dict[str, Any] = schema.get("properties", {})
    ground = _Grounding(source_text, instructions, quantities)
    data: dict[str, Any] = {}
    traces: list[FieldTrace] = []
    warnings: list[str] = []
    reported_missing: set[str] = set()

    for name, prop in properties.items():
        proposal = mapping.fields.get(name)
        value, trace, field_warnings = _normalize_field(name, prop if isinstance(prop, dict) else {}, proposal, ground)
        traces.append(trace)
        warnings.extend(field_warnings)
        if proposal is not None and proposal.missing:
            reported_missing.add(name)
        if value is None:
            types = allowed_types(prop if isinstance(prop, dict) else {})
            if trace.status == "missing":
                if _nullable(types):
                    warnings.append(f"{name}: not present in source; set to null")
                else:
                    warnings.append(f"{name}: not present in source; left out because the schema does not allow null")
            if _nullable(types):
                data[name] = None
        else:
            data[name] = value

    for extra in mapping.unknown_fields:
        warnings.append(f"model returned unknown field {extra!r}; ignored")
    warnings.extend(f"model note: {w}" for w in mapping.warnings)
    return NormalizedObject(data=data, traces=traces, warnings=_dedupe(warnings), reported_missing=reported_missing)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
