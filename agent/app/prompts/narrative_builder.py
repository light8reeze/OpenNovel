from app.schemas.narrative import NarrativeRequest

from app.prompts.system_rules import SYSTEM_RULES


def build_narrative_prompts(kind: str, request: NarrativeRequest) -> tuple[str, str]:
    system_prompt = SYSTEM_RULES + """
너의 역할은 engine이 확정한 결과를 바탕으로 장면 묘사와 선택지를 JSON으로 출력하는 것이다.
출력 형식:
{
  "narrative": "string",
  "choices": ["string", "string"],
  "source": "llm",
  "used_fallback": false,
  "safety_flags": []
}
"""

    outcome_block = """장면 시작이다. 아직 engine result는 없다."""
    if request.engine_result:
        outcome_block = f"""Resolved outcome:
- success: {request.engine_result.success}
- message_code: {request.engine_result.message_code}
- location_changed: {request.engine_result.location_changed}
- quest_stage_changed: {request.engine_result.quest_stage_changed}
- ending_reached: {request.engine_result.ending_reached or "-"}
- details: {", ".join(request.engine_result.details) or "-"}"""

    user_prompt = f"""Kind: {kind}

Current State Summary:
- turn: {request.state_summary.turn}
- location_id: {request.state_summary.location_id}
- hp: {request.state_summary.hp}
- gold: {request.state_summary.gold}
- murder_case_stage: {request.state_summary.murder_case_stage}
- player_flags: {", ".join(request.state_summary.player_flags) or "-"}

Scene Context:
- location_name: {request.scene_context.location_name}
- npcs_in_scene: {", ".join(request.scene_context.npcs_in_scene) or "-"}
- visible_targets: {", ".join(request.scene_context.visible_targets) or "-"}

{outcome_block}

Allowed choices:
{chr(10).join(f"- {choice}" for choice in request.allowed_choices)}

규칙:
- allowed_choices에 없는 선택지를 생성하지 마라.
- 한국어로 응답하라.
- 분위기는 dark fantasy mystery이되 과장된 시적 표현은 피한다.
- choice는 2개 이상 4개 이하로 유지한다.
"""
    return system_prompt, user_prompt
