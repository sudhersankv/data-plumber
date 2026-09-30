from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: Literal["text", "json", "csv"]
    data: Any = Field(description="A string for text/csv. For json: an object, an array, or a JSON string.")


class AdaptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Source
    target_schema: dict[str, Any] = Field(description="JSON Schema (draft 2020-12) the output must match.")
    instructions: str | None = Field(default=None, max_length=2000)


class AdaptResponse(BaseModel):
    data: Any
    valid: bool
    warnings: list[str]
    trace: list[dict[str, Any]] | None = None
    repaired: bool | None = None
