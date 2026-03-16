from app.prompts.intent_builder import build_intent_prompts
from app.prompts.narrative_builder import build_narrative_prompts
from app.retrieval.schemas import RetrievalContext, RetrievalHit
from app.schemas.common import ActionType, EngineResult, SceneContext, StateSummary
from app.schemas.intent import IntentValidationRequest
from app.schemas.narrative import NarrativeRequest


def test_narrative_prompt_includes_dynamic_scene_sections() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(
            turn=3,
            location_id="collapsed_hall",
            hp=52,
            gold=15,
            sunken_ruins_stage=2,
            player_flags=["found_rune"],
        ),
        scene_context=SceneContext(
            location_name="Collapsed Hall",
            npcs_in_scene=[],
            visible_targets=["trap_room", "ruins_entrance", "torch"],
        ),
        engine_result=EngineResult(
            success=True,
            message_code="TRAP_REVEALED",
            location_changed=False,
            quest_stage_changed=False,
            ending_reached=None,
            details=["floor_grooves"],
        ),
        allowed_choices=["주변을 조사한다", "함정방으로 이동한다", "입구로 돌아간다"],
    )
    retrieval = RetrievalContext(
        used=True,
        query="trap hall",
        hits=[RetrievalHit(id="narrator-trap", text="함정은 발견 직후보다 통과를 결심할 때 더 무섭다.", metadata={})],
    )

    system_prompt, user_prompt = build_narrative_prompts("turn", request, retrieval)

    assert "이번 턴의 장면은 반드시 한 걸음 전진해야 한다." in system_prompt
    assert "Game Objective:" in user_prompt
    assert "- long_term: 함정과 봉인 구조를 넘어 성소에 도달한다" in user_prompt
    assert "Obstacle Pressure:" in user_prompt
    assert "- physical_hazard: 함정이나 붕괴 위험이 안전한 전진을 가로막는다" in user_prompt
    assert "Resolution Modes:" in user_prompt
    assert "- investigate: 단서, 패턴, 안전 경로를 알아내서 푼다" in user_prompt
    assert "Scene Trajectory:" in user_prompt
    assert "- phase: discovery" in user_prompt
    assert "- forward_vector: 정보 발견" in user_prompt
    assert "Current Pressure:" in user_prompt
    assert "- danger_level: medium" in user_prompt
    assert "Unresolved Threads:" in user_prompt
    assert "Choice Composition Rules:" in user_prompt
    assert "allowed choices는 UI가 보여주는 즉시 추천 선택지" in user_prompt
    assert "directive: 안전 정보 발견과 동시에 다음 실수의 비용을 느끼게 하라" in user_prompt


def test_opening_narrative_prompt_sets_entry_tension() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(
            turn=0,
            location_id="ruins_entrance",
            hp=100,
            gold=15,
            sunken_ruins_stage=0,
            player_flags=[],
        ),
        scene_context=SceneContext(
            location_name="Sunken Ruins Entrance",
            npcs_in_scene=["caretaker"],
            visible_targets=["hall", "caretaker", "torch"],
        ),
        allowed_choices=["주변을 조사한다", "관리인과 대화한다", "회랑으로 이동한다"],
    )

    _, user_prompt = build_narrative_prompts("opening", request, RetrievalContext())

    assert "Game Objective:" in user_prompt
    assert "- long_term: 유적 깊숙한 곳의 유물을 확보하고 살아서 돌아온다" in user_prompt
    assert "- phase: opening" in user_prompt
    assert "- scene_goal: 유적 진입의 긴장과 탐험 동기를 설정" in user_prompt
    assert "- novelty_guardrail: 분위기 소개에 머물지 말고 진입 직전의 긴장을 남겨라" in user_prompt
    assert "directive: 장면의 진입 압박과 호기심을 동시에 세팅하라." in user_prompt


def test_intent_prompt_includes_phase_motives_and_target_vocabulary() -> None:
    request = IntentValidationRequest(
        player_input="관리인에게 다시 묻는다",
        allowed_actions=[ActionType.TALK, ActionType.INVESTIGATE],
        state_summary=StateSummary(
            turn=1,
            location_id="ruins_entrance",
            hp=100,
            gold=15,
            sunken_ruins_stage=0,
            player_flags=[],
        ),
        scene_context=SceneContext(
            location_name="Sunken Ruins Entrance",
            npcs_in_scene=["caretaker"],
            visible_targets=["hall", "caretaker", "torch"],
        ),
    )
    retrieval = RetrievalContext(
        used=True,
        query="caretaker warning",
        hits=[RetrievalHit(id="intent-caretaker", text="관리인은 위험 앞에서 정보를 주는 대상이다.", metadata={})],
    )

    system_prompt, user_prompt = build_intent_prompts(request, retrieval)

    assert "너의 역할은 플레이어 입력을 가장 적절한 action type으로 정규화하는 것이다." in system_prompt
    assert "Game Objective:" in user_prompt
    assert "- long_term: 유적 깊숙한 곳의 유물을 확보하고 무사히 돌아온다" in user_prompt
    assert "Obstacle Pressure:" in user_prompt
    assert "- knowledge_gap: 봉인 구조를 이해할 단서가 아직 부족하다" in user_prompt
    assert "Current Situation:" in user_prompt
    assert "- phase: descent" in user_prompt
    assert "Target Vocabulary:" in user_prompt
    assert "hall, caretaker, torch" in user_prompt
    assert "Likely Player Motives:" in user_prompt
    assert "- NPC에게 정보를 얻거나 반응을 확인" in user_prompt
    assert "Ambiguity Resolution Policy:" in user_prompt
    assert "플레이어 입력은 이전 turn의 suggested choice와 일치하지 않아도 된다." in user_prompt
    assert "정보가 부족한 장애물은 INVESTIGATE 쪽으로" in user_prompt
