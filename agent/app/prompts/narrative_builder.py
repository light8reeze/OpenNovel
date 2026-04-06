from __future__ import annotations

import json
from pathlib import Path

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
    npc_event_section = _npc_event_section(request)
    outcome_block = _outcome_block(request)
    player_style_section = _player_style_section(request)
    theme_style_hints = _theme_style_hints_section(request)
    if request.engine_result and request.engine_result.ending_reached:
        choices_section = "Allowed Choices:\n- (게임 종료 - 선택지 없음)"
    else:
        choices_section = f"Allowed Choices:\n{chr(10).join(f'- {choice}' for choice in request.allowed_choices) or '-'}"
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
- engine_result에 ending_reached가 있으면 그것이 최종 결말이다. 완료/성취 톤으로 마무리하고 미완료 표현을 쓰지 마라.
- 선택지는 서로 다른 접근법처럼 보이게 구성하라.
- narrative 안에 다음 선택지로 이어지는 환경적 단서를 자연스럽게 포함시켜라.
- 선택지 문구를 직접 언급하지 말고, 감각적 묘사로 힌트만 제공하라.
- 힌트 예시: MOVE→'복도 끝에서 물소리가 들린다', TALK→'그의 눈빛이 무언가를 말하고 있다', INVESTIGATE→'발밑에 살피지 못한 흔적이 보인다'
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

{player_style_section}{theme_style_hints}Player Discoveries:
{chr(10).join(f"- {fact}" for fact in request.discovery_log[-5:]) or "-"}

Retrieval Context:
{retrieval_block}

{npc_event_section}

{outcome_block}

Choice Composition Rules:
- 아래 allowed choices만 사용할 것
- allowed choices는 지금 상황에서 자연스럽게 떠오르는 즉시 제안이다
- narrative는 자유 입력의 가능성을 열어 둬야 한다
- 서로 다른 접근법이 느껴지도록 구성한다
- 선택지는 2개 이상 4개 이하
- narrative에 각 선택지로 이어지는 환경적 단서를 자연스럽게 포함시켜라
- 선택지 문구('~로 이동한다', '~와 대화한다')를 직접 사용하지 마라
- 감각(소리, 빛, 냄새, 시선)이나 상황 묘사로 힌트를 암시하라

{choices_section}

Output Contract:
- 한국어로 응답하라
- narrative는 2~4문장
- allowed_choices에 없는 선택지를 생성하지 마라
- 현재 세계관과 location_name에 맞는 어휘를 유지하라
"""
    return system_prompt, user_prompt


def _player_style_section(request: NarrativeRequest) -> str:
    style_tags = [tag.strip() for tag in request.state_summary.style_tags if tag.strip()]
    if not style_tags:
        return ""
    return f"""Player Style:
- accumulated_tags: {", ".join(style_tags)}
- directive: 위 성향이 플레이어가 반복해서 보여 준 접근법처럼 장면의 어조와 즉시 떠오르는 선택지에 스며들게 하라

"""


def _theme_style_hints_section(request: NarrativeRequest) -> str:
    theme_pack = _load_theme_pack(request.state_summary.theme_id)
    if not theme_pack:
        return ""
    style_hints = theme_pack.get("style_narrative_hints")
    if not isinstance(style_hints, dict):
        return ""
    matching_hints: list[str] = []
    for tag in request.state_summary.style_tags:
        hint = style_hints.get(tag)
        if isinstance(hint, str) and hint.strip():
            matching_hints.append(f"- {tag}: {hint.strip()}")
    if not matching_hints:
        return ""
    return f"""Theme Style Hints:
{chr(10).join(matching_hints)}

"""


def _load_theme_pack(theme_id: str | None) -> dict[str, object] | None:
    if not theme_id:
        return None
    theme_packs_path = Path(__file__).resolve().parents[3] / "content" / "theme_packs.json"
    if not theme_packs_path.exists():
        return None
    try:
        payload = json.loads(theme_packs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for item in payload:
        if isinstance(item, dict) and item.get("id") == theme_id:
            return item
    return None


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


def _npc_event_section(request: NarrativeRequest) -> str:
    if not request.engine_result:
        return "NPC Events:\n-"
    event_lines: list[str] = []
    for detail in request.engine_result.details:
        if not detail.startswith("npc_event:"):
            continue
        parts = detail.split(":", 3)
        if len(parts) >= 4:
            _, npc_id, action, message = parts
            event_lines.append(f"- {npc_id} / {action}: {message}")
        else:
            event_lines.append(f"- {detail}")
    return f"NPC Events:\n{chr(10).join(event_lines) or '-'}"


def _outcome_block(request: NarrativeRequest) -> str:
    if not request.engine_result:
        return """Resolved Outcome:
- opening turn
- 아직 engine result는 없다
- directive: 첫 장면의 압박과 호기심을 세팅하라"""

    ending_directive = ""
    if request.engine_result.ending_reached:
        ending_directive = f"""

⚠️ ENDING DIRECTIVE:
- 이번 턴에 엔딩 '{request.engine_result.ending_reached}'에 도달했다
- 반드시 결말/완료/성취 톤으로 마무리하라
- "아직", "완전히 ~않았다", "다음 행동을 결정해야 한다" 같은 미완료 표현 금지
- 플레이어의 여정이 의미 있게 마무리되었음을 전달하라"""

    return f"""Resolved Outcome:
- success: {request.engine_result.success}
- message_code: {request.engine_result.message_code}
- location_changed: {request.engine_result.location_changed}
- quest_stage_changed: {request.engine_result.quest_stage_changed}
- ending_reached: {request.engine_result.ending_reached or "-"}
- details: {", ".join(request.engine_result.details) or "-"}{ending_directive}"""
