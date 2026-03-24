from __future__ import annotations

import json

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
        "world_blueprint": request.world_blueprint.model_dump(mode="json"),
        "current_state": request.state.model_dump(mode="json"),
        "discovery_log": request.discovery_log[-12:],
        "recent_history": [message.model_dump(mode="json") for message in request.history[-10:]],
        "intent": request.intent.model_dump(mode="json"),
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
