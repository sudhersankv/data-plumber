"""Step 6: exact JSON Schema validation of the adapted object."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from app.models.internal import AdaptError


def check_target_schema(schema: Any) -> None:
    if not isinstance(schema, dict) or not schema:
        raise AdaptError("target_schema must be a non-empty JSON Schema object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise AdaptError(f"target_schema is not a valid JSON Schema: {exc.message}") from exc


def validation_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        location = ".".join(str(p) for p in error.absolute_path)
        errors.append(f"{location}: {error.message}" if location else error.message)
    return errors


def missing_required(instance: Any, schema: dict[str, Any]) -> list[str]:
    if not isinstance(instance, dict):
        return []
    return [name for name in schema.get("required", []) if name not in instance or instance[name] is None]
