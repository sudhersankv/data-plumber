from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = "accounts/fireworks/models/gpt-oss-120b"
DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"


@dataclass(frozen=True)
class Settings:
    fireworks_api_key: str
    fireworks_model: str
    fireworks_base_url: str
    llm_timeout_s: float


def get_settings() -> Settings:
    return Settings(
        fireworks_api_key=os.getenv("FIREWORKS_API_KEY", "").strip(),
        fireworks_model=os.getenv("FIREWORKS_MODEL", "").strip() or DEFAULT_MODEL,
        fireworks_base_url=os.getenv("FIREWORKS_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "60")),
    )
