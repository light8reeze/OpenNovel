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
WORLD_BUILD_LOG = LOG_DIR / "world-build-results.jsonl"
STATE_PROPOSAL_LOG = LOG_DIR / "state-proposal-results.jsonl"
VALIDATION_LOG = LOG_DIR / "validation-results.jsonl"
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


def log_stage_result(
    stage: str,
    endpoint: str,
    request: dict[str, Any],
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": _timestamp(),
        "ts_unix_ms": _timestamp_unix_ms(),
        "service": "agent",
        "kind": f"{stage}_result",
        "stage": stage,
        "endpoint": endpoint,
        "request": request,
        "response": response,
    }
    entry.update(_normalized_context(context))
    _append_jsonl(_stage_log_path(stage), entry)
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
    world_build_entries = _matching_entries(WORLD_BUILD_LOG, session_id, turn)
    state_proposal_entries = _matching_entries(STATE_PROPOSAL_LOG, session_id, turn)
    validation_entries = _matching_entries(VALIDATION_LOG, session_id, turn)
    narrative_entries = _matching_entries(NARRATIVE_LOG, session_id, turn)

    latest_game = game_entries[-1] if game_entries else None
    latest_intent = intent_entries[-1] if intent_entries else None
    latest_world_build = world_build_entries[-1] if world_build_entries else None
    latest_state_proposal = state_proposal_entries[-1] if state_proposal_entries else None
    latest_validation = validation_entries[-1] if validation_entries else None
    latest_narrative = narrative_entries[-1] if narrative_entries else None
    turn_token_usage = _sum_token_usage(
        [latest_world_build, latest_intent, latest_state_proposal, latest_narrative]
    )
    session_token_usage = _session_token_usage(session_id, turn)

    return {
        "found": any((latest_game, latest_intent, latest_world_build, latest_state_proposal, latest_validation, latest_narrative)),
        "sessionId": session_id,
        "turn": turn,
        "gameRequest": latest_game["request"] if latest_game else None,
        "gameResponse": latest_game["response"] if latest_game else None,
        "worldBuildRequest": latest_world_build["request"] if latest_world_build else None,
        "worldBuildResponse": latest_world_build["response"] if latest_world_build else None,
        "intentRequest": latest_intent["request"] if latest_intent else None,
        "intentResponse": latest_intent["response"] if latest_intent else None,
        "stateProposalRequest": latest_state_proposal["request"] if latest_state_proposal else None,
        "stateProposalResponse": latest_state_proposal["response"] if latest_state_proposal else None,
        "validationRequest": latest_validation["request"] if latest_validation else None,
        "validationResponse": latest_validation["response"] if latest_validation else None,
        "narrativeRequest": latest_narrative["request"] if latest_narrative else None,
        "narrativeResponse": latest_narrative["response"] if latest_narrative else None,
        "provider": _first_defined(
            _dig(latest_narrative, "response", "provider"),
            _dig(latest_state_proposal, "response", "provider"),
            _dig(latest_world_build, "response", "provider"),
            _dig(latest_intent, "response", "provider"),
        ),
        "model": _first_defined(
            _dig(latest_narrative, "response", "model"),
            _dig(latest_state_proposal, "response", "model"),
            _dig(latest_world_build, "response", "model"),
            _dig(latest_intent, "response", "model"),
        ),
        "usedFallback": _dig(latest_narrative, "response", "used_fallback"),
        "turnTokenUsage": turn_token_usage,
        "sessionTokenUsage": session_token_usage,
        "errorSummary": _build_error_summary(latest_intent, latest_narrative),
    }


def list_debug_sessions(limit: int = 20) -> list[dict[str, Any]]:
    if not GAME_LOG.exists():
        return []

    sessions: dict[str, dict[str, Any]] = {}
    with GAME_LOG.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = payload.get("sessionId")
            if not isinstance(session_id, str):
                continue
            turn = payload.get("turn", 0)
            ts = payload.get("ts")
            ts_unix_ms = payload.get("ts_unix_ms", 0)
            request = payload.get("request", {}) if isinstance(payload.get("request"), dict) else {}
            response = payload.get("response", {}) if isinstance(payload.get("response"), dict) else {}
            story_setup_id = response.get("storySetupId") or request.get("storySetupId")
            location_id = _dig(response, "state", "player", "location_id")
            message_code = _dig(response, "engineResult", "message_code")
            if not message_code and payload.get("endpoint") == "/game/start":
                message_code = "GAME_STARTED"

            current = sessions.get(session_id)
            if current is None:
                sessions[session_id] = {
                    "sessionId": session_id,
                    "storySetupId": story_setup_id,
                    "startedAt": ts,
                    "startedAtUnixMs": ts_unix_ms,
                    "latestTurn": int(turn) if isinstance(turn, int) else 0,
                    "lastLocationId": location_id,
                    "lastMessageCode": message_code,
                    "_latestTs": ts_unix_ms,
                }
                continue

            if current.get("storySetupId") is None and story_setup_id:
                current["storySetupId"] = story_setup_id
            if ts_unix_ms < current.get("startedAtUnixMs", ts_unix_ms):
                current["startedAt"] = ts
                current["startedAtUnixMs"] = ts_unix_ms
            if isinstance(turn, int) and turn >= current.get("latestTurn", 0):
                current["latestTurn"] = turn
            if ts_unix_ms >= current.get("_latestTs", 0):
                current["lastLocationId"] = location_id
                current["lastMessageCode"] = message_code
                current["_latestTs"] = ts_unix_ms

    items = sorted(sessions.values(), key=lambda item: item.get("_latestTs", 0), reverse=True)
    for item in items:
        item.pop("_latestTs", None)
    return items[:limit]


def list_debug_turns(session_id: str) -> list[dict[str, Any]]:
    entries = _matching_entries_until_turn(GAME_LOG, session_id, 10**9)
    if not entries:
        return []

    turns: dict[int, dict[str, Any]] = {}
    for entry in entries:
        turn = entry.get("turn")
        if not isinstance(turn, int):
            continue
        response = entry.get("response", {}) if isinstance(entry.get("response"), dict) else {}
        state = response.get("state", {}) if isinstance(response.get("state"), dict) else {}
        player = state.get("player", {}) if isinstance(state.get("player"), dict) else {}
        engine_result = response.get("engineResult", {}) if isinstance(response.get("engineResult"), dict) else {}
        message_code = engine_result.get("message_code")
        if not message_code and entry.get("endpoint") == "/game/start":
            message_code = "GAME_STARTED"
        turns[turn] = {
            "turn": turn,
            "timestamp": entry.get("ts"),
            "messageCode": message_code,
            "locationId": player.get("location_id"),
            "storySetupId": response.get("storySetupId"),
            "input": _debug_input_summary(entry.get("request", {}), turn),
        }

    return [turns[key] for key in sorted(turns)]


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


def _matching_entries_until_turn(path: Path, session_id: str, turn: int) -> list[dict[str, Any]]:
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
            if payload.get("sessionId") == session_id and isinstance(payload.get("turn"), int) and payload["turn"] <= turn:
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


def _debug_input_summary(request: dict[str, Any] | None, turn: int) -> str:
    if turn == 0:
        return "새 세션 시작"
    if not isinstance(request, dict):
        return ""
    return request.get("inputText") or request.get("choiceText") or ""


def _stage_log_path(stage: str) -> Path:
    mapping = {
        "world_build": WORLD_BUILD_LOG,
        "state_proposal": STATE_PROPOSAL_LOG,
        "validation": VALIDATION_LOG,
    }
    return mapping[stage]


def _extract_token_usage(entry: dict[str, Any] | None) -> dict[str, int]:
    usage = _dig(entry, "response", "token_usage")
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated": False}
    return {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
        "estimated": bool(usage.get("estimated", False)),
    }


def _sum_token_usage(entries: list[dict[str, Any] | None]) -> dict[str, Any]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated": False}
    for entry in entries:
        usage = _extract_token_usage(entry)
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            totals[key] += usage[key]
        totals["estimated"] = totals["estimated"] or usage["estimated"]
    return totals


def _latest_entries_by_turn(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for entry in entries:
        turn = entry.get("turn")
        if isinstance(turn, int):
            latest[turn] = entry
    return [latest[turn] for turn in sorted(latest)]


def _session_token_usage(session_id: str, turn: int) -> dict[str, Any]:
    latest_world_builds = _latest_entries_by_turn(_matching_entries_until_turn(WORLD_BUILD_LOG, session_id, turn))
    latest_intents = _latest_entries_by_turn(_matching_entries_until_turn(INTENT_LOG, session_id, turn))
    latest_state_proposals = _latest_entries_by_turn(_matching_entries_until_turn(STATE_PROPOSAL_LOG, session_id, turn))
    latest_narratives = _latest_entries_by_turn(_matching_entries_until_turn(NARRATIVE_LOG, session_id, turn))
    world_build_totals = _sum_token_usage(latest_world_builds)
    intent_totals = _sum_token_usage(latest_intents)
    proposal_totals = _sum_token_usage(latest_state_proposals)
    narrative_totals = _sum_token_usage(latest_narratives)
    return {
        "worldBuild": world_build_totals,
        "intent": intent_totals,
        "stateProposal": proposal_totals,
        "narrative": narrative_totals,
        "combined": {
            "input_tokens": world_build_totals["input_tokens"] + intent_totals["input_tokens"] + proposal_totals["input_tokens"] + narrative_totals["input_tokens"],
            "output_tokens": world_build_totals["output_tokens"] + intent_totals["output_tokens"] + proposal_totals["output_tokens"] + narrative_totals["output_tokens"],
            "total_tokens": world_build_totals["total_tokens"] + intent_totals["total_tokens"] + proposal_totals["total_tokens"] + narrative_totals["total_tokens"],
            "estimated": world_build_totals["estimated"] or intent_totals["estimated"] or proposal_totals["estimated"] or narrative_totals["estimated"],
        },
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_unix_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
