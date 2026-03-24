from __future__ import annotations

import json

from app.schemas.multi_agent import WorldBuildRequest


def build_world_builder_prompts(request: WorldBuildRequest) -> tuple[str, str]:
    setup = request.story_setup
    system_prompt = "\n".join(
        [
            "You are a world builder for a Korean interactive fiction game.",
            "Return valid JSON only.",
            "Create one coherent world blueprint for a single game session.",
            "Keep the world playable immediately from the opening scene.",
            "Do not write prose outside JSON.",
        ]
    )
    payload = {
        "story_setup": setup.model_dump(mode="json"),
        "requirements": [
            "Respect the provided world_summary, tone, player_goal, and opening_hook.",
            "Return a world blueprint that can be validated by a deterministic runtime.",
            "Create 3 to 5 locations with short Korean labels and explicit connections.",
            "Create 1 to 3 important NPCs with labels and home locations.",
            "Keep hidden_truths short and concrete.",
        ],
        "output_schema": {
            "id": "snake_case",
            "title": "string",
            "world_summary": "string",
            "tone": "string",
            "core_conflict": "string",
            "player_goal": "string",
            "opening_hook": "string",
            "starting_location_id": "location_id",
            "locations": [
                {
                    "id": "snake_case",
                    "label": "string",
                    "kind": "string",
                    "connections": ["other_location_id"],
                    "danger_level": 1,
                    "investigation_hooks": ["string"],
                }
            ],
            "npcs": [
                {
                    "id": "snake_case",
                    "label": "string",
                    "home_location_id": "location_id",
                    "role": "string",
                    "interaction_hint": "string",
                }
            ],
            "notable_locations": ["string"],
            "important_npcs": ["string"],
            "hidden_truths": ["string"],
        },
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False, indent=2)
