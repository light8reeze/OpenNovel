from __future__ import annotations

import json
from pathlib import Path

from app.schemas.multi_agent import StoryTransitionProposalRequest


def build_state_manager_prompts(request: StoryTransitionProposalRequest) -> tuple[str, str]:
    system_prompt = "\n".join(
        [
            "You propose the next story transition for a Korean interactive fiction game.",
            "You are not the final authority. The validator will accept, correct, or reject your proposal.",
            "Return valid JSON only.",
            "State changes must be small, local, and consistent with the current canon state.",
            "Choice candidates must be concise Korean strings.",
            "Different action types must produce meaningfully different proposals.",
        ]
    )
    payload = {
        "world_blueprint": _summarize_world_blueprint(request),
        "current_state": request.state.model_dump(mode="json"),
        "discovery_log": request.discovery_log[-5:],
        "intent": request.intent.model_dump(mode="json"),
        "allowed_actions": _allowed_actions(request),
        "location_connections": _location_connections(request),
        "available_actions": _available_actions_section(request),
        "victory_conditions_summary": _victory_conditions_summary(request),
        "victory_paths": _victory_paths_section(request),
        "choice_candidate_rules": [
            "Base every choice candidate on the Available Actions section.",
            "MOVE choices must only use connected_locations from location_connections.",
            "INVESTIGATE choices should reflect current_location_hooks when hooks remain.",
            "TALK choices should only target npcs currently present in this location.",
            "USE_ITEM and REST choices should only appear when they would plausibly matter this turn.",
        ],
        "requirements": [
            "Propose the next scene and only a partial state patch.",
            "Do not rewrite the entire state.",
            "Discovered facts must be facts the player could plausibly learn this turn.",
            "Choice candidates should suggest 2 to 4 next moves.",
            "INVESTIGATE should reveal clues or signal that the area is exhausted.",
            "TALK should change social information, trust, or disclosed facts.",
            "MOVE should emphasize entering pressure, risk, or opportunity in a new place.",
            "REST and USE_ITEM should reorganize resources or clarity more than story stage.",
            "If the player repeats the same ineffective action, mark the scene as stalled instead of inventing major progress.",
            "If victory conditions are met (correct action + location + stage), reflect completion tone in scene_summary.",
        ],
        "output_schema": {
            "scene_summary": "string",
            "state_patch": {"optional_nested_state": "partial patch"},
            "discovered_facts": ["string"],
            "choice_candidates": ["string"],
            "risk_tags": ["string"],
        },
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False, indent=2)


def _summarize_world_blueprint(request: StoryTransitionProposalRequest) -> dict[str, object]:
    current_location = next(
        (
            location
            for location in request.world_blueprint.locations
            if location.id == request.state.player.location_id
        ),
        None,
    )
    return {
        "id": request.world_blueprint.id,
        "title": request.world_blueprint.title,
        "tone": request.world_blueprint.tone,
        "core_conflict": request.world_blueprint.core_conflict,
        "theme_id": request.world_blueprint.theme_id,
        "locations": [
            {
                "id": location.id,
                "label": location.label,
                "connections": location.connections,
            }
            for location in request.world_blueprint.locations
        ],
        "npcs": [
            {
                "id": npc.id,
                "label": npc.label,
            }
            for npc in request.world_blueprint.npcs
        ],
        "current_location_hooks": current_location.investigation_hooks if current_location else [],
    }


def build_state_proposal_prompts(request: StoryTransitionProposalRequest) -> tuple[str, str]:
    return build_state_manager_prompts(request)


def _allowed_actions(request: StoryTransitionProposalRequest) -> list[str]:
    current_location = _current_location(request)
    actions = ["INVESTIGATE"]
    if _current_npcs(request):
        actions.append("TALK")
    if current_location and current_location.connections:
        actions.append("MOVE")
    if request.state.player.inventory:
        actions.append("USE_ITEM")
    actions.append("REST")
    return actions


def _location_connections(request: StoryTransitionProposalRequest) -> dict[str, object]:
    current_location = _current_location(request)
    return {
        "current_location_id": request.state.player.location_id,
        "current_location_label": current_location.label if current_location else request.state.player.location_id,
        "connected_locations": [
            {
                "id": location.id,
                "label": location.label,
            }
            for location in _connected_locations(request)
        ],
    }


def _available_actions_section(request: StoryTransitionProposalRequest) -> list[dict[str, object]]:
    current_location = _current_location(request)
    current_npcs = _current_npcs(request)
    connected_locations = _connected_locations(request)
    return [
        {
            "action_type": "INVESTIGATE",
            "guidance": "Use current location hooks to propose clue-driven investigation choices.",
            "hooks": current_location.investigation_hooks if current_location else [],
        },
        {
            "action_type": "TALK",
            "guidance": "Only propose TALK if there are NPCs in the current location.",
            "npcs": [npc.label for npc in current_npcs],
        },
        {
            "action_type": "MOVE",
            "guidance": "Only propose MOVE toward directly connected locations.",
            "connections": [location.label for location in connected_locations],
        },
        {
            "action_type": "USE_ITEM",
            "guidance": "Use inventory items or theme-resolution actions when they plausibly change clarity or pressure.",
            "inventory": request.state.player.inventory,
        },
        {
            "action_type": "REST",
            "guidance": "REST should be a low-momentum regrouping option.",
        },
    ]


def _victory_paths_section(request: StoryTransitionProposalRequest) -> list[dict[str, object]]:
    theme_id = request.world_blueprint.theme_id
    if not theme_id:
        return []
    theme_pack = _load_theme_pack(theme_id)
    if not theme_pack:
        return []
    return [
        {
            "path_id": path.get("id", ""),
            "required_action": path.get("required_action", ""),
            "required_location": _resolve_required_location_label(request, path.get("required_location_index", -1)),
            "min_stage": path.get("min_stage", 0),
        }
        for path in theme_pack.get("victory_paths", [])
        if isinstance(path, dict)
    ]


def _victory_conditions_summary(request: StoryTransitionProposalRequest) -> str:
    paths = _victory_paths_section(request)
    if not paths:
        return ""
    return " | ".join(
        (
            f"{path['path_id']}: "
            f"action={path['required_action']}, "
            f"location={path['required_location']}, "
            f"min_stage={path['min_stage']}"
        )
        for path in paths
    )


def _current_location(request: StoryTransitionProposalRequest):
    return next(
        (
            location
            for location in request.world_blueprint.locations
            if location.id == request.state.player.location_id
        ),
        None,
    )


def _current_npcs(request: StoryTransitionProposalRequest):
    return [
        npc
        for npc in request.world_blueprint.npcs
        if npc.home_location_id == request.state.player.location_id
    ]


def _connected_locations(request: StoryTransitionProposalRequest):
    current_location = _current_location(request)
    if not current_location:
        return []
    return [
        location
        for location in request.world_blueprint.locations
        if location.id in current_location.connections
    ]


def _load_theme_pack(theme_id: str) -> dict[str, object] | None:
    theme_packs_path = Path(__file__).resolve().parents[3] / "content" / "theme_packs.json"
    if not theme_packs_path.exists():
        return None
    try:
        payload = json.loads(theme_packs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for item in payload:
        if isinstance(item, dict) and item.get("id") == theme_id:
            return item
    return None


def _resolve_required_location_label(request: StoryTransitionProposalRequest, required_index: object) -> str:
    if not request.world_blueprint.locations:
        return request.state.player.location_id
    if not isinstance(required_index, int):
        return request.state.player.location_id
    resolved_index = _resolve_required_location_index(request, required_index)
    location = request.world_blueprint.locations[resolved_index]
    return location.label


def _resolve_required_location_index(request: StoryTransitionProposalRequest, required_index: int) -> int:
    if required_index >= 0:
        return min(required_index, len(request.world_blueprint.locations) - 1)
    if required_index == -1:
        return _climax_location_index(request)
    return max(0, len(request.world_blueprint.locations) + required_index)


def _climax_location_index(request: StoryTransitionProposalRequest) -> int:
    locations = request.world_blueprint.locations
    highest_danger = max(location.danger_level for location in locations)
    for index in range(len(locations) - 1, -1, -1):
        if locations[index].danger_level == highest_danger:
            return index
    return max(0, len(locations) - 1)
