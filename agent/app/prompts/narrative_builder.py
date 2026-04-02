from app.schemas.narrative import NarrativeRequest
from app.retrieval.schemas import RetrievalContext

from app.prompts.system_rules import SYSTEM_RULES


def build_narrative_prompts(
    kind: str,
    request: NarrativeRequest,
    retrieval: RetrievalContext,
) -> tuple[str, str]:
    retrieval_block = retrieval.as_prompt_block() or "-"
    world_title = request.world_title or "dynamic story world"
    world_summary = request.world_summary or "플레이어는 현재 세계의 갈등 속에서 다음 단서를 찾아야 한다."
    world_tone = request.world_tone or "긴장된 모험"
    player_goal = request.player_goal or "현재 세계의 핵심 갈등을 풀 단서를 찾아야 한다."
    opening_hook = request.opening_hook or "첫 장면부터 플레이어를 즉시 끌어들인다."
    scene_phase = _scene_phase(kind, request)
    game_objective = _game_objective(kind, request)
    pressure = _pressure(request)
    unresolved_threads = _unresolved_threads(request)
    outcome_block = _outcome_block(request)
    system_prompt = SYSTEM_RULES + """
너의 역할은 validator가 확정한 결과를 바탕으로 장면 묘사와 선택지를 JSON으로 출력하는 것이다.
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
- 세계관에 없는 던전 상투어를 임의로 끌어오지 마라.
- validated_scene_summary가 있으면 그 장면 방향과 사건 결과를 우선 반영하라.
- progress_kind가 stalled이면 억지 진전을 만들지 말고, 왜 정체되었는지 자연스럽게 드러내라.
- 선택지는 서로 다른 접근법처럼 보이게 구성하라.
"""

    user_prompt = f"""Campaign Frame:
- title: {world_title}
- world_summary: {world_summary}
- player_goal: {player_goal}
- tone: {world_tone}
- opening_hook: {opening_hook}
- style: concise Korean prose

Story Objective:
{game_objective}

Current Scene:
- kind: {kind}
- phase: {scene_phase}
- progress_kind: {request.progress_kind or "-"}
- turn: {request.state_summary.turn}
- location_id: {request.state_summary.location_id}
- location_name: {request.scene_context.location_name}
- story_arc_stage: {request.state_summary.story_arc_stage}
- theme_id: {request.state_summary.theme_id or "-"}
- hp: {request.state_summary.hp}
- gold: {request.state_summary.gold}
- player_flags: {", ".join(request.state_summary.player_flags) or "-"}
- npcs_in_scene: {", ".join(request.scene_context.npcs_in_scene) or "-"}
- visible_targets: {", ".join(request.scene_context.visible_targets) or "-"}
- validated_scene_summary: {request.scene_summary or "-"}

Current Pressure:
{pressure}

Unresolved Threads:
{unresolved_threads}

Player Discoveries:
{chr(10).join(f"- {fact}" for fact in request.discovery_log[-5:]) or "-"}

Retrieval Context:
{retrieval_block}

{outcome_block}

Choice Composition Rules:
- 아래 allowed choices만 사용할 것
- allowed choices는 지금 상황에서 자연스럽게 떠오르는 즉시 제안이다
- narrative는 자유 입력의 가능성을 열어 둬야 한다
- 서로 다른 접근법이 느껴지도록 구성한다
- 선택지는 2개 이상 4개 이하

Allowed Choices:
{chr(10).join(f"- {choice}" for choice in request.allowed_choices)}

Output Contract:
- 한국어로 응답하라
- narrative는 2~4문장
- allowed_choices에 없는 선택지를 생성하지 마라
- 현재 세계관과 location_name에 맞는 어휘를 유지하라
"""
    return system_prompt, user_prompt


def _scene_phase(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "opening"
    stage = request.state_summary.story_arc_stage
    if stage <= 1:
        return "entry"
    if stage <= 3:
        return "exploration"
    if stage <= 5:
        return "pressure"
    return "late"


def _game_objective(kind: str, request: NarrativeRequest) -> str:
    if kind == "opening":
        return "\n".join(
            [
                "- long_term: 현재 세계의 핵심 갈등을 마주하고 해결의 실마리를 찾는다",
                "- immediate: 첫 장면에서 전진 동기와 호기심을 동시에 만든다",
            ]
        )
    stage = request.state_summary.story_arc_stage
    if stage <= 2:
        return "\n".join(
            [
                "- long_term: 갈등의 중심에 가까워질 단서와 관계를 확보한다",
                "- immediate: 지금 위치에서 유의미한 다음 행동을 설득력 있게 제시한다",
            ]
        )
    return "\n".join(
        [
            "- long_term: 지금까지 드러난 갈등을 해결 가능한 방향으로 밀어붙인다",
            "- immediate: 위험, 정보, 관계 중 무엇을 우선할지 분명하게 만든다",
        ]
    )


def _pressure(request: NarrativeRequest) -> str:
    pressures: list[str] = []
    if request.state_summary.hp <= 60:
        pressures.append("- resource_pressure: 체력과 여유가 줄어들고 있다")
    if request.scene_context.npcs_in_scene:
        pressures.append("- social_pressure: 인물과의 접촉이 상황을 바꿀 수 있다")
    if len(request.scene_context.visible_targets) >= 2:
        pressures.append("- branching_pressure: 다음 선택지가 여러 방향으로 열려 있다")
    if request.engine_result:
        pressures.append(f"- outcome_pressure: 직전 결과는 {request.engine_result.message_code}였다")
    if not pressures:
        pressures.append("- ambient_pressure: 지금 장면은 다음 행동을 요구하고 있다")
    return "\n".join(pressures)


def _unresolved_threads(request: NarrativeRequest) -> str:
    threads: list[str] = []
    if request.scene_summary:
        threads.append(f"- validated_scene: {request.scene_summary}")
    if request.scene_context.npcs_in_scene:
        threads.append(f"- active_people: {', '.join(request.scene_context.npcs_in_scene)}")
    if request.scene_context.visible_targets:
        threads.append(f"- open_paths: {', '.join(request.scene_context.visible_targets)}")
    return "\n".join(threads)


def _outcome_block(request: NarrativeRequest) -> str:
    if not request.engine_result:
        return """Resolved Outcome:
- opening turn
- 아직 engine result는 없다
- directive: 첫 장면의 압박과 호기심을 세팅하라"""
    return f"""Resolved Outcome:
- success: {request.engine_result.success}
- message_code: {request.engine_result.message_code}
- location_changed: {request.engine_result.location_changed}
- quest_stage_changed: {request.engine_result.quest_stage_changed}
- ending_reached: {request.engine_result.ending_reached or "-"}
- details: {", ".join(request.engine_result.details) or "-"}"""
