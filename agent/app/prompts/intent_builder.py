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
- 최종 판정은 engine이 수행한다.

Player Input:
{request.player_input}

Current Situation:
- phase: {scene_phase}
- turn: {request.state_summary.turn}
- location_id: {request.state_summary.location_id}
- hp: {request.state_summary.hp}
- gold: {request.state_summary.gold}
- sunken_ruins_stage: {request.state_summary.sunken_ruins_stage}
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
- 플레이어 입력은 이전 turn의 suggested choice와 일치하지 않아도 된다.
- suggested choice에 없던 자유 입력도 현재 allowed_actions, visible_targets, scene context를 기준으로 해석한다.
- allowed_actions 밖의 action_type을 내면 안 된다.
- visible_targets에 없는 target은 내면 안 된다.
- 플레이어는 보통 조사해서 푼다, 설득해서 푼다, 아이템을 써서 푼다, 대가를 감수하고 뚫는다 중 하나를 시도한다고 가정한다.
- 정보가 부족한 장애물은 INVESTIGATE 쪽으로, 사람을 통한 해법은 TALK 쪽으로, 장비 활용은 USE_ITEM 쪽으로, 위험 감수는 MOVE 또는 FLEE 쪽으로 우선 해석한다.
- 문장이 모호하면 현재 장면 phase와 visible_targets를 기준으로 가장 보수적인 해석을 한다.
- 그래도 불명확하면 INVESTIGATE로 낮은 confidence를 준다.
- 이동 target은 반드시 현재 visible_targets vocabulary를 사용한다.

Output Contract:
- JSON only
- confidence는 0.0 ~ 1.0
- raw_input은 반드시 원문 유지
"""
    return system_prompt, user_prompt


def _scene_phase(request: IntentValidationRequest) -> str:
    stage = request.state_summary.sunken_ruins_stage
    if request.state_summary.turn == 0:
        return "opening"
    if stage <= 1:
        return "descent"
    if stage <= 3:
        return "discovery"
    if stage <= 5:
        return "confrontation"
    return "extraction"


def _likely_motives(request: IntentValidationRequest) -> str:
    motives: list[str] = []
    if request.state_summary.hp <= 40:
        motives.append("- 생존과 위험 관리")
    if request.scene_context.npcs_in_scene:
        motives.append("- NPC에게 정보를 얻거나 반응을 확인")
    if any(target in request.scene_context.visible_targets for target in ("sanctum", "trap_room", "hall")):
        motives.append("- 더 깊은 구역으로 전진")
    if "torch" in request.scene_context.visible_targets:
        motives.append("- 자원 점검 및 시야 확보")
    if not motives:
        motives.append("- 주변 정보 수집")
    return "\n".join(motives)


def _game_objective(request: IntentValidationRequest) -> str:
    stage = request.state_summary.sunken_ruins_stage
    if stage == 0:
        return "\n".join(
            [
                "- long_term: 유적 깊숙한 곳의 유물을 확보하고 무사히 돌아온다",
                "- immediate: 입구 단서와 관리인의 정보를 바탕으로 진입 경로를 판단한다",
            ]
        )
    if stage == 1:
        return "\n".join(
            [
                "- long_term: 봉인을 열고 유물에 도달할 수 있는 경로를 완성한다",
                "- immediate: 더 깊은 구역으로 들어가기 위한 단서와 안전 경로를 확보한다",
            ]
        )
    if stage <= 3:
        return "\n".join(
            [
                "- long_term: 봉인 구조를 해제하고 핵심 구역까지 진입한다",
                "- immediate: 함정과 회랑의 패턴을 파악해 안전하게 전진한다",
            ]
        )
    if stage <= 5:
        return "\n".join(
            [
                "- long_term: 유물을 확보한 뒤 유적의 대가를 감당하며 탈출한다",
                "- immediate: 봉인 해제 이후의 위험 속에서 유물 확보와 퇴각 판단을 한다",
            ]
        )
    return "\n".join(
        [
            "- long_term: 유물 회수 결과를 지키고 생존한다",
            "- immediate: 탈출, 보존, 후속 대응 중 무엇이 남았는지 정리한다",
        ]
    )


def _obstacle_pressure(request: IntentValidationRequest) -> str:
    stage = request.state_summary.sunken_ruins_stage
    flags = set(request.state_summary.player_flags)
    pressures: list[str] = []
    if stage == 0:
        pressures.append("- entrance_gate: 어디로 진입해야 안전한지 아직 불명확하다")
    if "found_rune" not in flags:
        pressures.append("- knowledge_gap: 봉인 구조를 이해할 단서가 아직 부족하다")
    if request.state_summary.location_id in {"collapsed_hall", "trap_room"} and "trap_revealed" not in flags:
        pressures.append("- physical_hazard: 안전 경로를 모르면 함정 위험이 크다")
    if request.state_summary.hp <= 40:
        pressures.append("- resource_pressure: 체력이 낮아 무리한 돌파의 비용이 크다")
    if request.scene_context.npcs_in_scene:
        pressures.append("- social_route: NPC 대화가 우회 해법이 될 수 있다")
    if not pressures:
        pressures.append("- active_obstacle: 다음 선택이 장기 목표를 어떻게 전진시키는지가 핵심이다")
    return "\n".join(pressures)
