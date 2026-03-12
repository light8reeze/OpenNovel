from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class RoleModelSettings:
    provider: str
    model: str
    base_url: Optional[str]
    api_key: Optional[str]
    timeout_seconds: float


@dataclass(frozen=True)
class VectorStoreSettings:
    provider: str
    persist_directory: Path
    collection_prefix: str
    auto_index_on_startup: bool
    top_k: int


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class Settings:
    intender: RoleModelSettings
    narrator: RoleModelSettings
    vector_store: VectorStoreSettings
    embedding: EmbeddingSettings


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    return Settings(
        intender=_load_role_settings("INTENDER", default_model="gpt-4.1-mini"),
        narrator=_load_role_settings("NARRATOR", default_model="gpt-4.1-mini"),
        vector_store=VectorStoreSettings(
            provider=_env("AGENT_VECTOR_DB_PROVIDER", "chroma").lower(),
            persist_directory=(root / _env("AGENT_VECTOR_DB_PATH", ".chroma")).resolve(),
            collection_prefix=_env("AGENT_VECTOR_COLLECTION_PREFIX", "opennovel"),
            auto_index_on_startup=_env("AGENT_VECTOR_AUTO_INDEX", "true").lower()
            in {"1", "true", "yes"},
            top_k=int(_env("AGENT_VECTOR_TOP_K", "4")),
        ),
        embedding=EmbeddingSettings(
            provider=_env("AGENT_EMBEDDING_PROVIDER", "local-hash").lower(),
            model=_env("AGENT_EMBEDDING_MODEL", "local-hash-v1"),
            dimensions=int(_env("AGENT_EMBEDDING_DIMENSIONS", "64")),
        ),
    )


def _load_role_settings(role: str, default_model: str) -> RoleModelSettings:
    provider = _env(f"AGENT_{role}_PROVIDER", "mock").lower()
    model = _env(f"AGENT_{role}_MODEL", default_model if provider != "mock" else "mock")
    base_url = _optional_env(f"AGENT_{role}_BASE_URL")
    api_key = (
        _optional_env(f"AGENT_{role}_API_KEY")
        or _optional_env("AGENT_LLM_API_KEY")
        or _optional_env("OPENAI_API_KEY")
        or _optional_env("GEMINI_API_KEY")
    )
    timeout_seconds = float(_env(f"AGENT_{role}_TIMEOUT_SECONDS", "15"))
    return RoleModelSettings(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )


def _env(key: str, default: str) -> str:
    return os.getenv(key, default).strip() or default


def _optional_env(key: str) -> Optional[str]:
    value = os.getenv(key, "").strip()
    return value or None
