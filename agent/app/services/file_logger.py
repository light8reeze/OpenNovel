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
LLM_LOG = LOG_DIR / "llm-errors.jsonl"


def log_backend_request(
    endpoint: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "backend_request",
        "endpoint": endpoint,
        "payload": payload,
    }
    entry.update(_normalized_context(context))
    _append_jsonl(REQUEST_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_intent_result(
    endpoint: str,
    request: dict[str, Any],
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "intent_result",
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    entry.update(_normalized_context(context))
    _append_jsonl(INTENT_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_narrative_result(
    endpoint: str,
    request: dict[str, Any],
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "narrative_result",
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    entry.update(_normalized_context(context))
    _append_jsonl(NARRATIVE_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_game_result(
    endpoint: str,
    request: dict[str, Any],
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "game_result",
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    entry.update(_normalized_context(context))
    _append_jsonl(GAME_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def log_llm_error(
    role: str,
    provider: str,
    model: str,
    stage: str,
    error: str,
    extra: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": "llm_error",
        "role": role,
        "provider": provider,
        "model": model,
        "stage": stage,
        "error": error,
        "extra": extra or {},
    }
    _append_jsonl(LLM_LOG, entry)
    _append_jsonl(COMBINED_LOG, entry)


def load_turn_log_bundle(session_id: str, turn: int) -> dict[str, Any]:
    game_entries = _matching_entries(GAME_LOG, session_id, turn)
    intent_entries = _matching_entries(INTENT_LOG, session_id, turn)
    narrative_entries = _matching_entries(NARRATIVE_LOG, session_id, turn)

    latest_game = game_entries[-1] if game_entries else None
    latest_intent = intent_entries[-1] if intent_entries else None
    latest_narrative = narrative_entries[-1] if narrative_entries else None

    return {
        "found": any((latest_game, latest_intent, latest_narrative)),
        "sessionId": session_id,
        "turn": turn,
        "gameRequest": latest_game["request"] if latest_game else None,
        "gameResponse": latest_game["response"] if latest_game else None,
        "intentRequest": latest_intent["request"] if latest_intent else None,
        "intentResponse": latest_intent["response"] if latest_intent else None,
        "narrativeRequest": latest_narrative["request"] if latest_narrative else None,
        "narrativeResponse": latest_narrative["response"] if latest_narrative else None,
        "provider": _first_defined(
            _dig(latest_narrative, "response", "provider"),
            _dig(latest_intent, "response", "provider"),
        ),
        "model": _first_defined(
            _dig(latest_narrative, "response", "model"),
            _dig(latest_intent, "response", "model"),
        ),
        "usedFallback": _dig(latest_narrative, "response", "used_fallback"),
        "errorSummary": _build_error_summary(latest_intent, latest_narrative),
    }


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False))
        file.write("\n")


def _matching_entries(path: Path, session_id: str, turn: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("sessionId") == session_id and payload.get("turn") == turn:
                entries.append(payload)
    entries.sort(key=lambda item: item.get("ts_unix_ms", 0))
    return entries


def _normalized_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    normalized = dict(context)
    if "session_id" in normalized and "sessionId" not in normalized:
        normalized["sessionId"] = normalized.pop("session_id")
    return normalized


def _dig(payload: dict[str, Any] | None, *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _build_error_summary(
    latest_intent: dict[str, Any] | None,
    latest_narrative: dict[str, Any] | None,
) -> dict[str, Any] | None:
    summary: dict[str, Any] = {}
    intent_flags = _dig(latest_intent, "response", "validation_flags") or []
    narrative_flags = _dig(latest_narrative, "response", "safety_flags") or []
    if intent_flags:
        summary["intentValidationFlags"] = intent_flags
    if narrative_flags:
        summary["narrativeSafetyFlags"] = narrative_flags
    return summary or None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_unix_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
