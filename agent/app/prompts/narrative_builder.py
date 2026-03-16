from app.schemas.narrative import NarrativeRequest
from app.retrieval.schemas import RetrievalContext

from app.prompts.system_rules import SYSTEM_RULES


def build_narrative_prompts(
    kind: str,
    request: NarrativeRequest,
    retrieval: RetrievalContext,
) -> tuple[str, str]:
    retrieval_block = retrieval.as_prompt_block() or "-"
    scene_phase = _scene_phase(kind, request)
    game_objective = _game_objective(kind, request)
    obstacle_pressure = _obstacle_pressure(request)
    resolution_modes = _resolution_modes(request)
    scene_goal = _scene_goal(kind, request)
    forward_vector = _forward_vector(kind, request)
    danger_level = _danger_level(request)
    unresolved_threads = _unresolved_threads(request)
    novelty_guardrail = _novelty_guardrail(kind, request)
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

추가 규칙:
- 이번 턴의 장면은 반드시 한 걸음 전진해야 한다.
- 직전 outcome의 의미를 반복 설명하지 말고, 장면의 압박이나 방향을 한 단계 진전시켜라.
- 선택지는 서로 다른 접근법처럼 보이게 구성하라.
"""

    outcome_block = """Resolved Outcome:
- opening turn
- 아직 engine result는 없다.
- directive: 장면의 진입 압박과 호기심을 동시에 세팅하라."""
    if request.engine_result:
        outcome_block = f"""Resolved Outcome:
- success: {request.engine_result.success}
- message_code: {request.engine_result.message_code}
- location_changed: {request.engine_result.location_changed}
- quest_stage_changed: {request.engine_result.quest_stage_changed}
- ending_reached: {request.engine_result.ending_reached or "-"}
- details: {", ".join(request.engine_result.details) or "-"}
- directive: {_outcome_directive(request)}"""

    user_prompt = f"""Campaign Frame:
- genre: dark ruins exploration
- style: concise Korean prose
- tone: tense, ancient, dangerous
- avoid: purple prose, repetitive summary, overexplaining known facts

Game Objective:
{game_objective}

Obstacle Pressure:
{obstacle_pressure}

Resolution Modes:
{resolution_modes}

Scene Trajectory:
- kind: {kind}
- phase: {scene_phase}
- scene_goal: {scene_goal}
- forward_vector: {forward_vector}
- novelty_guardrail: {novelty_guardrail}

Current Pressure:
- danger_level: {danger_level}
- resource_pressure: {_resource_pressure(request)}
- social_pressure: {_social_pressure(request)}

Player-Known Truth:
- turn: {request.state_summary.turn}
- location_id: {request.state_summary.location_id}
- hp: {request.state_summary.hp}
- gold: {request.state_summary.gold}
- sunken_ruins_stage: {request.state_summary.sunken_ruins_stage}
- player_flags: {", ".join(request.state_summary.player_flags) or "-"}
- location_name: {request.scene_context.location_name}
- npcs_in_scene: {", ".join(request.scene_context.npcs_in_scene) or "-"}
- visible_targets: {", ".join(request.scene_context.visible_targets) or "-"}

Unresolved Threads:
{unresolved_threads}

Retrieval Context:
{retrieval_block}

{outcome_block}

Choice Composition Rules:
- 아래 allowed choices만 사용할 것
- allowed choices는 UI가 보여주는 즉시 추천 선택지이며, 플레이어가 시도할 수 있는 모든 행동의 전체 목록은 아니다.
- narrative는 플레이어가 자유 입력으로 다른 행동을 시도할 수도 있다는 열린 감각을 해치지 않아야 한다.
- 가능한 한 전진 선택 1개, 정보/조사 선택 1개, 위험 관리 또는 후퇴 선택 1개를 우선한다.
- 가능하면 선택지에서 장애물을 푸는 방식이 다르게 느껴지게 하라: 알아내기, 설득하기, 사용하기, 감수하고 돌파하기.
- 같은 결의 선택지를 반복하지 말고 접근법이 다르게 느껴지게 구성한다.
- 선택지는 2개 이상 4개 이하로 유지한다.

Allowed Choices:
{chr(10).join(f"- {choice}" for choice in request.allowed_choices)}

Output Contract:
- 한국어로 응답하라.
- narrative는 2~4문장으로 유지한다.
- allowed_choices에 없는 선택지를 생성하지 마라.
- 현재 모드는 시나리오 진행이 비활성화된 샌드박스이므로 quest stage나 엔딩을 새롭게 암시하지 마라.
"""
    return system_prompt, user_prompt


def _scene_phase(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "opening"
    stage = request.state_summary.sunken_ruins_stage
    if stage <= 1:
        return "descent"
    if stage <= 3:
        return "discovery"
    if stage <= 5:
        return "confrontation"
    return "extraction"


def _scene_goal(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "유적 진입의 긴장과 탐험 동기를 설정"
    stage = request.state_summary.sunken_ruins_stage
    if stage <= 1:
        return "더 깊은 구역으로 들어가야 할 이유를 강화"
    if stage <= 3:
        return "봉인과 위험의 구조를 점점 선명하게 드러냄"
    if stage <= 5:
        return "핵심 결단이나 대가를 체감하게 만듦"
    return "회수 또는 퇴각의 결말 감각을 형성"


def _game_objective(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "\n".join(
            [
                "- long_term: 유적 깊숙한 곳의 유물을 확보하고 살아서 돌아온다",
                "- immediate: 입구를 넘어 탐험을 시작할 명확한 동기와 긴장을 만든다",
            ]
        )
    stage = request.state_summary.sunken_ruins_stage
    if stage <= 1:
        return "\n".join(
            [
                "- long_term: 봉인을 풀 수 있는 경로를 확보해 유물에 도달한다",
                "- immediate: 입구 단서와 초기 경로를 확보해 더 깊은 구역으로 내려간다",
            ]
        )
    if stage <= 3:
        return "\n".join(
            [
                "- long_term: 함정과 봉인 구조를 넘어 성소에 도달한다",
                "- immediate: 안전 경로와 위험 패턴을 파악해 전진의 기반을 만든다",
            ]
        )
    if stage <= 5:
        return "\n".join(
            [
                "- long_term: 유물을 확보하고 붕괴 직전의 유적에서 빠져나온다",
                "- immediate: 봉인 해제 이후의 대가를 감수할지 후퇴할지 결정하게 만든다",
            ]
        )
    return "\n".join(
        [
            "- long_term: 회수한 결과를 지키고 생존을 확정한다",
            "- immediate: 귀환 또는 퇴각 이후의 여운과 비용을 남긴다",
        ]
    )


def _obstacle_pressure(request: NarrativeRequest) -> str:
    stage = request.state_summary.sunken_ruins_stage
    flags = set(request.state_summary.player_flags)
    pressures: list[str] = []
    if stage == 0:
        pressures.append("- entrance_gate: 진입 자체가 첫 번째 장애물이다")
    if "found_rune" not in flags:
        pressures.append("- knowledge_gap: 봉인과 유적 구조를 해석할 정보가 아직 부족하다")
    if request.state_summary.location_id in {"collapsed_hall", "trap_room"} and "trap_revealed" not in flags:
        pressures.append("- physical_hazard: 함정이나 붕괴 위험이 안전한 전진을 가로막는다")
    if request.state_summary.hp <= 40:
        pressures.append("- resource_pressure: 생존 자원이 부족해 무리한 전진의 비용이 크다")
    if request.scene_context.npcs_in_scene:
        pressures.append("- social_route: NPC가 정보나 경고를 통해 우회 해법이 될 수 있다")
    if request.engine_result and request.engine_result.message_code in {"SEAL_BROKEN", "CURSE_TRIGGERED"}:
        pressures.append("- supernatural_cost: 전진할수록 저주와 봉인의 반동이 커진다")
    if not pressures:
        pressures.append("- active_obstacle: 다음 선택이 목표를 얼마나 안전하게 전진시키는지가 핵심이다")
    return "\n".join(pressures)


def _resolution_modes(request: NarrativeRequest) -> str:
    modes: list[str] = [
        "- investigate: 단서, 패턴, 안전 경로를 알아내서 푼다",
        "- talk: NPC나 관계를 활용해 설득하거나 힌트를 얻어 푼다",
    ]
    if "torch" in request.scene_context.visible_targets or "torch_lit" in request.state_summary.player_flags:
        modes.append("- use_item: 아이템과 도구를 써서 시야나 안전을 확보한다")
    modes.append("- push_through: 대가를 감수하고 돌파하거나 후퇴를 결단한다")
    return "\n".join(modes)


def _forward_vector(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "호기심과 진입 압박"
    if not request.engine_result:
        return "상황 전진"
    code = request.engine_result.message_code
    if code in {"MOVE_OK", "PASSAGE_OPENED"}:
        return "공간 전진"
    if code in {"RUNE_FOUND", "TRAP_REVEALED"}:
        return "정보 발견"
    if code in {"SEAL_BROKEN", "CURSE_TRIGGERED"}:
        return "위험 증폭"
    if code in {"RELIC_SECURED", "RELIC_RECOVERED", "RETREAT_END"}:
        return "목표 회수 또는 탈출 결말"
    return "선택 압박"


def _danger_level(request: NarrativeRequest) -> str:
    if request.state_summary.hp <= 35:
        return "high"
    if request.state_summary.sunken_ruins_stage >= 4:
        return "high"
    if request.state_summary.hp <= 60 or request.state_summary.sunken_ruins_stage >= 2:
        return "medium"
    return "low"


def _resource_pressure(request: NarrativeRequest) -> str:
    if request.state_summary.hp <= 35:
        return "체력이 낮아 후퇴와 자원 관리 압박이 크다"
    if "torch_lit" not in request.state_summary.player_flags:
        return "시야 확보와 안전 확인이 아직 중요하다"
    return "즉시 자원 압박은 낮지만 더 깊이 갈수록 대가가 커질 수 있다"


def _social_pressure(request: NarrativeRequest) -> str:
    if "caretaker_warned" in request.state_summary.player_flags:
        return "관리인의 경고가 아직 판단에 그림자를 드리운다"
    if request.scene_context.npcs_in_scene:
        return "NPC 반응이 다음 판단과 정보 공개 수준에 영향을 준다"
    return "사회적 압박은 낮고 환경 자체의 위협이 중심이다"


def _unresolved_threads(request: NarrativeRequest) -> str:
    threads: list[str] = []
    stage = request.state_summary.sunken_ruins_stage
    flags = set(request.state_summary.player_flags)
    if stage == 0:
        threads.append("- 유적 입구의 첫 단서와 진입 이유가 아직 완전히 정리되지 않았다")
    if "found_rune" not in flags:
        threads.append("- 봉인 구조를 설명할 결정적 룬을 아직 확보하지 못했다")
    if "opened_passage" not in flags and stage >= 1:
        threads.append("- 더 깊은 구역으로 이어지는 길이 완전히 열리지 않았다")
    if "trap_revealed" not in flags and request.state_summary.location_id in {"collapsed_hall", "trap_room"}:
        threads.append("- 함정의 질서와 안전 경로가 아직 불분명하다")
    if stage >= 4:
        threads.append("- 유물을 확보할지 물러설지에 대한 결단이 가까워지고 있다")
    if not threads:
        threads.append("- 장면의 즉시 갈등은 엔진 결과 이후의 반응과 다음 선택에 있다")
    return "\n".join(threads)


def _novelty_guardrail(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "분위기 소개에 머물지 말고 진입 직전의 긴장을 남겨라"
    if not request.engine_result:
        return "직전 설명 반복 금지"
    code = request.engine_result.message_code
    if code in {"MOVE_OK", "PASSAGE_OPENED"}:
        return "단순 이동 설명에 머물지 말고 공간 변화가 의미하는 다음 위험을 드러내라"
    if code in {"RUNE_FOUND", "TRAP_REVEALED"}:
        return "단서를 요약만 하지 말고 그것이 부르는 다음 판단의 부담을 남겨라"
    if code in {"SEAL_BROKEN", "CURSE_TRIGGERED"}:
        return "위험을 서술하되 공포 문장 반복보다 즉시 선택 압박을 강조하라"
    return "직전 결과 설명을 반복하지 말고 다음 결정을 밀어라"


def _outcome_directive(request: NarrativeRequest) -> str:
    if not request.engine_result:
        return "진입 전의 긴장과 호기심을 설정하라"
    code = request.engine_result.message_code
    mapping = {
        "MOVE_OK": "새 구역의 공기와 위험 감각을 통해 장면을 한 단계 이동시켜라",
        "RUNE_FOUND": "단서의 의미를 암시하고 다음 탐색 필요성을 높여라",
        "PASSAGE_OPENED": "새 길이 열린 안도감보다 그 너머의 압박을 강조하라",
        "TRAP_REVEALED": "안전 정보 발견과 동시에 다음 실수의 비용을 느끼게 하라",
        "SEAL_BROKEN": "봉인 해제의 충격과 즉시 닥친 결단을 밀어라",
        "RELIC_SECURED": "성공보다 대가와 탈출 압박을 남겨라",
        "RELIC_RECOVERED": "회수의 성취와 여진을 함께 보여라",
        "CARETAKER_BRIEFING": "정보 전달을 사건의 방향 전환처럼 느끼게 하라",
        "CARETAKER_WARNING": "경고가 앞으로의 리스크 판단에 남도록 하라",
        "CURSE_TRIGGERED": "후퇴가 더 이상 안전하지 않다는 반전을 강조하라",
        "RETREAT_END": "퇴각의 끝이 안식이 아니라 여운과 비용으로 남게 하라",
    }
    return mapping.get(code, "결과를 요약하지 말고 다음 장면의 압박으로 전환하라")
