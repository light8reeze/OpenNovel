from app.schemas.intent import IntentValidationRequest
from app.retrieval.schemas import RetrievalContext

from app.prompts.system_rules import SYSTEM_RULES


def build_intent_prompts(
    request: IntentValidationRequest,
    retrieval: RetrievalContext,
) -> tuple[str, str]:
    retrieval_block = retrieval.as_prompt_block() or "-"
    system_prompt = SYSTEM_RULES + """
너의 역할은 플레이어 입력을 가장 적절한 action type으로 정규화하는 것이다.
최종 판정 권한은 backend에 있다.
출력 형식:
{
  "action": {
    "action_type": "MOVE|TALK|ATTACK|INVESTIGATE|REST|USE_ITEM|FLEE|TRADE",
    "target": "string|null",
    "raw_input": "원문"
  },
  "confidence": 0.0,
  "validation_flags": ["..."],
  "source": "llm"
}
"""

    user_prompt = f"""플레이어 입력:
{request.player_input}

허용 액션:
{", ".join(action.value for action in request.allowed_actions)}

현재 상태:
- turn: {request.state_summary.turn}
- location_id: {request.state_summary.location_id}
- hp: {request.state_summary.hp}
- gold: {request.state_summary.gold}
- sunken_ruins_stage: {request.state_summary.sunken_ruins_stage}
- player_flags: {", ".join(request.state_summary.player_flags) or "-"}

장면 정보:
- location_name: {request.scene_context.location_name}
- npcs_in_scene: {", ".join(request.scene_context.npcs_in_scene) or "-"}
- visible_targets: {", ".join(request.scene_context.visible_targets) or "-"}

retrieval context:
{retrieval_block}

규칙:
- allowed_actions 밖의 action_type을 내면 안 된다.
- visible_targets에 없는 target은 내면 안 된다.
- 모호하면 INVESTIGATE로 낮은 confidence를 준다.
- retrieval context는 힌트일 뿐이며 입력/상태보다 우선하면 안 된다.
- 이동 target은 `hall`, `trap_room`, `sanctum`, `ruins_entrance`, `caretaker`, `torch` 같은 현재 visible_targets vocabulary만 사용한다.
"""
    return system_prompt, user_prompt
