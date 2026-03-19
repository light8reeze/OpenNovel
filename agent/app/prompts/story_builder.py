from __future__ import annotations

import json

from app.schemas.story import StoryTurnRequest
from app.retrieval.schemas import RetrievalContext


def build_story_prompts(request: StoryTurnRequest, context: RetrievalContext) -> tuple[str, str]:
    system_prompt = "\n".join(
        [
            "You are the story engine for a text-based interactive novel game.",
            "You decide the next scene, the next lightweight state snapshot, and the next player choices.",
            "Keep the world consistent with the provided history and current state.",
            "Return valid JSON only.",
            "Do not wrap the JSON in markdown fences.",
            "Preserve the overall response schema exactly.",
            "Choices must contain 2 to 4 concise Korean options.",
            "State is a lightweight compatibility state for the UI, not a strict simulation.",
            "The state field may be a partial patch that only includes changed fields, but it must stay JSON-object shaped.",
            "If the player input is free-form, infer the most plausible action and update the scene naturally.",
        ]
    )

    payload = {
        "mode": request.mode,
        "current_state": request.state.model_dump(mode="json"),
        "history": [message.model_dump(mode="json") for message in request.history[-10:]],
        "player_input": request.player_input,
        "retrieval_context": context.as_prompt_block(),
        "output_schema": {
            "narrative": "string",
            "choices": ["string"],
            "state": "GameState-compatible object",
            "engineResult": "EngineResult-compatible object",
            "action": {"action_type": "MOVE|TALK|INVESTIGATE|REST|USE_ITEM|FLEE|ATTACK|TRADE", "target": "optional"},
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)
    return system_prompt, user_prompt
