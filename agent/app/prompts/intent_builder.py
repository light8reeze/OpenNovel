from app.schemas.intent import IntentValidationRequest
from app.retrieval.schemas import RetrievalContext

from app.prompts.system_rules import SYSTEM_RULES


def build_intent_prompts(
    request: IntentValidationRequest,
    retrieval: RetrievalContext,
) -> tuple[str, str]:
    retrieval_block = retrieval.as_prompt_block() or "-"
    scene_phase = _scene_phase(request)
    game_objective = _game_objective(request)
    obstacle_pressure = _obstacle_pressure(request)
    likely_motives = _likely_motives(request)
    target_vocabulary = ", ".join(request.scene_context.visible_targets) or "-"
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

    user_prompt = f"""Role and Authority:
- 너는 intent normalizer다.
- 최종 판정은 validator가 수행한다.

Player Input:
{request.player_input}

Current Situation:
- phase: {scene_phase}
- turn: {request.state_summary.turn}
- location_id: {request.state_summary.location_id}
- hp: {request.state_summary.hp}
- gold: {request.state_summary.gold}
- story_arc_stage: {request.state_summary.story_arc_stage}
- player_flags: {", ".join(request.state_summary.player_flags) or "-"}
- location_name: {request.scene_context.location_name}
- npcs_in_scene: {", ".join(request.scene_context.npcs_in_scene) or "-"}

Game Objective:
{game_objective}

Obstacle Pressure:
{obstacle_pressure}

Allowed Actions:
{", ".join(action.value for action in request.allowed_actions)}

Target Vocabulary:
{target_vocabulary}

Likely Player Motives:
{likely_motives}

Retrieval Context:
{retrieval_block}

Ambiguity Resolution Policy:
- 플레이어 입력은 자유 입력일 수 있다.
- allowed_actions 밖의 action_type을 내면 안 된다.
- target은 visible_targets 또는 npcs_in_scene에 있는 표현만 사용한다.
- 사람에게 접근하는 입력은 TALK를, 장소로 향하는 입력은 MOVE를 우선 고려한다.
- 문장이 모호하면 현재 장면에서 가장 보수적인 해석을 한다.
- 그래도 불명확하면 INVESTIGATE로 낮은 confidence를 준다.

Output Contract:
- JSON only
- confidence는 0.0 ~ 1.0
- raw_input은 반드시 원문 유지
"""
    return system_prompt, user_prompt


def _scene_phase(request: IntentValidationRequest) -> str:
    stage = request.state_summary.story_arc_stage
    if request.state_summary.turn == 0:
        return "opening"
    if stage <= 1:
        return "entry"
    if stage <= 3:
        return "exploration"
    if stage <= 5:
        return "pressure"
    return "late"


def _likely_motives(request: IntentValidationRequest) -> str:
    motives: list[str] = []
    if request.state_summary.hp <= 40:
        motives.append("- 생존과 위험 관리")
    if request.scene_context.npcs_in_scene:
        motives.append("- 등장인물에게 정보를 얻거나 반응을 확인")
    if request.scene_context.visible_targets:
        motives.append("- 다른 장소나 단서로 전진")
    if "횃불" in request.scene_context.visible_targets:
        motives.append("- 시야 확보와 도구 활용")
    if not motives:
        motives.append("- 주변 정보 수집")
    return "\n".join(motives)


def _game_objective(request: IntentValidationRequest) -> str:
    stage = request.state_summary.story_arc_stage
    if stage <= 1:
        return "\n".join(
            [
                "- long_term: 현재 세계의 갈등과 목표를 밀고 나갈 단서를 확보한다",
                "- immediate: 지금 위치에서 가장 안전하고 유의미한 다음 행동을 판단한다",
            ]
        )
    if stage <= 3:
        return "\n".join(
            [
                "- long_term: 핵심 갈등에 가까워질 실마리와 관계를 확보한다",
                "- immediate: 다음 구역이나 다음 인물과 접촉할 이유를 강화한다",
            ]
        )
    return "\n".join(
        [
            "- long_term: 지금까지 드러난 갈등을 해결 가능한 방향으로 몰고 간다",
            "- immediate: 위험과 정보, 관계 중 어느 축을 우선할지 결정한다",
        ]
    )


def _obstacle_pressure(request: IntentValidationRequest) -> str:
    pressures: list[str] = []
    if request.state_summary.hp <= 40:
        pressures.append("- resource_pressure: 체력이 낮아 무리한 전진의 비용이 크다")
    if request.scene_context.npcs_in_scene:
        pressures.append("- social_route: 대화가 우회 해법이 될 수 있다")
    if request.scene_context.visible_targets:
        pressures.append("- branching_pressure: 선택할 수 있는 다음 지점이 여러 개다")
    if not pressures:
        pressures.append("- active_obstacle: 다음 선택이 장기 목표를 어떻게 전진시키는지가 핵심이다")
    return "\n".join(pressures)
