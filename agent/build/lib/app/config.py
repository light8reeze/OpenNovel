from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    llm_base_url: str | None
    llm_api_key: str | None
    llm_timeout_seconds: float


def load_settings() -> Settings:
    provider = os.getenv("AGENT_LLM_PROVIDER", "mock").strip().lower()
    model = os.getenv("AGENT_LLM_MODEL", "").strip()
    base_url = os.getenv("AGENT_LLM_BASE_URL", "").strip() or None
    api_key = (
        os.getenv("AGENT_LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or None
    )
    timeout_raw = os.getenv("AGENT_LLM_TIMEOUT_SECONDS", "15").strip() or "15"
    timeout_seconds = float(timeout_raw)

    default_model = {
        "openai": "gpt-4.1-mini",
        "openai_compatible": "gpt-4.1-mini",
        "gemini": "gemini-2.5-flash",
        "mock": "mock",
    }.get(provider, "mock")

    return Settings(
        llm_provider=provider,
        llm_model=model or default_model,
        llm_base_url=base_url,
        llm_api_key=api_key,
        llm_timeout_seconds=timeout_seconds,
    )
