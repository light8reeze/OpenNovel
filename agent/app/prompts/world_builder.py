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
            "Do not wrap the answer in markdown or extra keys.",
            "Return exactly one JSON object whose top-level keys match the blueprint fields.",
            "Do not repeat the input payload.",
        ]
    )
    payload = {
        "task": "Fill the blueprint object below. Keep all text in Korean. Use 3 to 5 locations and 1 to 3 NPCs.",
        "story_setup": {
            "id": setup.id,
            "title": setup.title,
            "world_summary": setup.world_summary,
            "tone": setup.tone,
            "player_goal": setup.player_goal,
            "opening_hook": setup.opening_hook,
        },
        "blueprint_template": {
            "id": setup.id,
            "title": setup.title,
            "world_summary": setup.world_summary,
            "tone": setup.tone,
            "core_conflict": setup.player_goal,
            "player_goal": setup.player_goal,
            "opening_hook": setup.opening_hook,
            "starting_location_id": "location_1",
            "locations": [
                {
                    "id": "location_1",
                    "label": "입구",
                    "kind": "location",
                    "connections": ["location_2"],
                    "danger_level": 1,
                    "investigation_hooks": ["수상한 흔적"],
                },
                {
                    "id": "location_2",
                    "label": "깊은 곳",
                    "kind": "location",
                    "connections": ["location_1", "location_3"],
                    "danger_level": 2,
                    "investigation_hooks": ["숨겨진 단서"],
                },
                {
                    "id": "location_3",
                    "label": "핵심 장소",
                    "kind": "location",
                    "connections": ["location_2"],
                    "danger_level": 3,
                    "investigation_hooks": ["결정적 실마리"],
                },
            ],
            "npcs": [
                {
                    "id": "guide",
                    "label": "안내자",
                    "home_location_id": "location_1",
                    "role": "guide",
                    "interaction_hint": "사건의 배경을 알고 있다.",
                }
            ],
            "notable_locations": ["입구", "깊은 곳", "핵심 장소"],
            "important_npcs": ["안내자"],
            "hidden_truths": ["겉으로 보이는 사건 뒤에 더 오래된 진실이 숨어 있다."],
        },
        "rules": [
            "Respect the provided story setup.",
            "Return only the filled blueprint object.",
            "Do not add keys named story_setup, requirements, output_schema, or blueprint_template.",
            "Every connection must reference another location id in the same object.",
        ],
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False, indent=2)
