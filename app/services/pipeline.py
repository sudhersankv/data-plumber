"""The adaptation pipeline: parse, annotate, map, normalize, validate, repair once."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.internal import AdaptError, AdaptResult, ParsedSource, trace_dict
from app.services.annotator import annotate
from app.services.llm_client import LLMClient
from app.services.llm_mapper import (
    MAPPING_RESPONSE_SCHEMA,
    MAX_SOURCE_CHARS,
    MalformedMappingError,
    build_messages,
    parse_mapping,
)
from app.services.normalizer import NormalizedObject, normalize
from app.services.parser import parse_source
from app.services.repair import repair_messages
from app.services.validator import check_target_schema, missing_required, validation_errors

logger = logging.getLogger("data_plumber")


def adapt(
    content_type: str,
    data: Any,
    target_schema: dict[str, Any],
    instructions: str | None,
    client: LLMClient,
) -> AdaptResult:
    check_target_schema(target_schema)
    source = parse_source(content_type, data)

    if _is_object_schema(target_schema):
        result = _adapt_object(source, target_schema, instructions, client)
        if isinstance(source.value, list) and len(source.value) > 1:
            result.warnings.insert(
                0, f"source is a list of {len(source.value)} items but target_schema is one object; mapped the list as a whole"
            )
        return result

    items_schema = target_schema.get("items") if target_schema.get("type") == "array" else None
    if isinstance(items_schema, dict) and _is_object_schema(items_schema):
        return _adapt_array(source, target_schema, items_schema, instructions, client)

    raise AdaptError('target_schema must describe an object with "properties", or an array whose "items" is such an object')


def _is_object_schema(schema: dict[str, Any]) -> bool:
    declared = schema.get("type")
    is_object = declared == "object" or (isinstance(declared, list) and "object" in declared)
    return is_object and isinstance(schema.get("properties"), dict) and bool(schema["properties"])


def _adapt_array(
    source: ParsedSource,
    schema: dict[str, Any],
    items_schema: dict[str, Any],
    instructions: str | None,
    client: LLMClient,
) -> AdaptResult:
    if isinstance(source.value, list):
        elements = [ParsedSource(source.content_type, item, json.dumps(item, ensure_ascii=False)) for item in source.value]
    else:
        elements = [source]

    rows: list[Any] = []
    warnings: list[str] = []
    trace: list[dict[str, Any]] = []
    repaired = False
    for index, element in enumerate(elements):
        result = _adapt_object(element, items_schema, instructions, client)
        rows.append(result.data)
        warnings.extend(f"[{index}] {w}" for w in result.warnings)
        trace.append({"index": index, "fields": result.trace})
        repaired = repaired or result.repaired

    errors = validation_errors(rows, schema)
    warnings.extend(f"schema: {e}" for e in errors)
    return AdaptResult(data=rows, valid=not errors, warnings=warnings, trace=trace, repaired=repaired)


def _adapt_object(
    source: ParsedSource,
    schema: dict[str, Any],
    instructions: str | None,
    client: LLMClient,
) -> AdaptResult:
    result = _map_object(source, schema, instructions, client)
    if len(source.text) > MAX_SOURCE_CHARS:
        result.warnings.insert(
            0,
            f"source: only the first {MAX_SOURCE_CHARS} of {len(source.text)} characters were read; later values may be missing",
        )
    return result


def _map_object(
    source: ParsedSource,
    schema: dict[str, Any],
    instructions: str | None,
    client: LLMClient,
) -> AdaptResult:
    properties = schema["properties"]
    quantities = annotate(source, instructions)
    messages = build_messages(source, schema, quantities, instructions)

    raw = client.complete(messages, MAPPING_RESPONSE_SCHEMA)
    first, problems = _attempt(raw, schema, properties, quantities, source, instructions)

    if first is not None and not problems:
        return _result(first, schema, repaired=False)

    if first is not None and _only_honest_gaps(first, schema, problems):
        return _result(first, schema, repaired=False)

    logger.info("repairing mapping: %s", problems)
    raw_retry = client.complete(repair_messages(messages, raw, problems), MAPPING_RESPONSE_SCHEMA)
    second, retry_problems = _attempt(raw_retry, schema, properties, quantities, source, instructions)
    if second is None:
        partial = first.data if first is not None else None
        warnings = (first.warnings if first is not None else []) + [
            f"mapping failed after one repair attempt: {p}" for p in retry_problems
        ]
        traces = [trace_dict(t) for t in first.traces] if first is not None else []
        return AdaptResult(data=partial, valid=False, warnings=warnings, trace=traces, repaired=True)
    return _result(second, schema, repaired=True)


def _attempt(
    raw: str,
    schema: dict[str, Any],
    properties: dict[str, Any],
    quantities: list,
    source: ParsedSource,
    instructions: str | None,
) -> tuple[NormalizedObject | None, list[str]]:
    try:
        mapping = parse_mapping(raw, properties)
    except MalformedMappingError as exc:
        return None, [str(exc)]
    normalized = normalize(mapping, schema, quantities, source.text, instructions)
    return normalized, validation_errors(normalized.data, schema)


def _only_honest_gaps(normalized: NormalizedObject, schema: dict[str, Any], problems: list[str]) -> bool:
    """True when validation only fails on required fields the model already reported as absent.

    Repairing would just ask the model to invent them, so the result is returned as invalid.
    """
    missing = set(missing_required(normalized.data, schema))
    required_errors = [p for p in problems if "is a required property" in p or "None is not of type" in p]
    return bool(missing) and len(required_errors) == len(problems) and missing <= normalized.reported_missing


def _result(normalized: NormalizedObject, schema: dict[str, Any], repaired: bool) -> AdaptResult:
    errors = validation_errors(normalized.data, schema)
    warnings = list(normalized.warnings)
    for name in missing_required(normalized.data, schema):
        warnings.append(f"{name}: required by target_schema but not found in source")
    warnings.extend(f"schema: {e}" for e in errors)
    traces = [trace_dict(t) for t in normalized.traces]
    for t in traces:
        logger.debug("trace %s", t)
    return AdaptResult(data=normalized.data, valid=not errors, warnings=warnings, trace=traces, repaired=repaired)
