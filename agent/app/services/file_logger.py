from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
LOG_ROOT = REPO_ROOT / "log"
LOG_DIR = LOG_ROOT / "agent"
RUN_ID = os.getenv("OPENNOVEL_RUN_ID", "manual")
COMBINED_LOG = LOG_ROOT / "combined" / f"run-{RUN_ID}.jsonl"
REQUEST_LOG = LOG_DIR / "backend-requests.jsonl"
INTENT_LOG = LOG_DIR / "intent-results.jsonl"
NARRATIVE_LOG = LOG_DIR / "narrative-results.jsonl"
GAME_LOG = LOG_DIR / "game-results.jsonl"


def log_backend_request(endpoint: str, payload: dict[str, Any]) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "backend_request",
        "endpoint": endpoint,
        "payload": payload,
    }
    _append_jsonl(REQUEST_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_intent_result(endpoint: str, request: dict[str, Any], response: dict[str, Any]) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "intent_result",
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    _append_jsonl(INTENT_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_narrative_result(endpoint: str, request: dict[str, Any], response: dict[str, Any]) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "narrative_result",
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    _append_jsonl(NARRATIVE_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_game_result(endpoint: str, request: dict[str, Any], response: dict[str, Any]) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "game_result",
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    _append_jsonl(GAME_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False))
        file.write("\n")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_unix_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
