from app.agents.narrator import NarratorAgent
from app.game.models import initial_state
from app.runtime import get_runtime
from app.schemas.common import Action, ActionType, EngineResult, SceneContext, StateSummary
from app.schemas.multi_agent import WorldBlueprint, WorldLocation, WorldNpc
from app.schemas.narrative import NarrativeRequest, NarrativeResponse


def test_validator_move_progress_ignores_proposal_added_visited_flag() -> None:
    runtime = get_runtime()
    validator = runtime.validator
    blueprint = WorldBlueprint(
        id="qa_move_regression",
        title="회랑 테스트",
        world_summary="이동 진행도를 검증한다.",
        tone="긴장",
        core_conflict="새 구역으로 진입한다.",
        player_goal="새 구역으로 이동한다.",
        opening_hook="회랑 앞에 선다.",
        starting_location_id="entrance",
        locations=[
            WorldLocation(id="entrance", label="입구", connections=["hall"]),
            WorldLocation(id="hall", label="회랑", connections=["entrance"]),
        ],
    )
    state = initial_state(seed=7)
    state.player.location_id = "entrance"
    state.player.flags = ["visited:entrance"]

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.MOVE, target="회랑", raw_input="회랑으로 이동한다"),
        proposal_summary="회랑이 눈앞에 열린다.",
        proposal_patch={"player": {"flags": ["visited:hall"]}},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.progress_kind == "move"
    assert result.state.player.location_id == "hall"
    assert result.state.quests.story_arc.stage == 1


def test_validator_talk_progress_ignores_proposal_added_talked_flag() -> None:
    runtime = get_runtime()
    validator = runtime.validator
    blueprint = WorldBlueprint(
        id="qa_talk_regression",
        title="광장 테스트",
        world_summary="대화 진행도를 검증한다.",
        tone="긴장",
        core_conflict="처음 대화로 단서를 얻는다.",
        player_goal="인물과 대화한다.",
        opening_hook="광장에 선다.",
        starting_location_id="square",
        locations=[WorldLocation(id="square", label="광장", connections=[])],
        npcs=[WorldNpc(id="elder", label="장로", home_location_id="square", interaction_hint="뭔가를 숨긴다.")],
    )
    state = initial_state(seed=9)
    state.player.location_id = "square"
    state.player.flags = ["visited:square"]

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.TALK, target="장로", raw_input="장로와 대화한다"),
        proposal_summary="장로가 숨겨 둔 이야기를 꺼낸다.",
        proposal_patch={"player": {"flags": ["talked:elder"]}},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.progress_kind == "talk"
    assert result.state.quests.story_arc.stage == 1
    assert "talked:elder" in result.state.player.flags


def test_narrator_completed_objective_returns_terminal_ending_without_choices() -> None:
    runtime = get_runtime()
    narrator = NarratorAgent(
        settings=runtime.narrator.settings,
        llm_client=runtime.intender.llm_client,
        retrieval=runtime.retrieval,
    )
    request = NarrativeRequest(
        state_summary=StateSummary(turn=7, location_id="well", hp=100, gold=15, story_arc_stage=3),
        scene_context=SceneContext(location_name="낡은 우물"),
        engine_result=EngineResult(
            success=True,
            message_code="OBJECTIVE_COMPLETED",
            location_changed=False,
            quest_stage_changed=False,
            ending_reached="sealed",
            details=["victory:sealed"],
        ),
        progress_kind="use_item",
        allowed_choices=["낡은 우물을 더 조사한다", "촌장의 집으로 이동한다"],
        scene_summary="의식이 마침내 닫힌다.",
    )
    response = NarrativeResponse(
        narrative="봉인하려던 의식은 실패했고, 오히려 무언가를 깨운 듯하다.",
        choices=["낡은 우물을 더 조사한다"],
        source="gemini_llm",
    )

    validated = narrator._validate("turn", response, request)

    assert validated.choices == []
    assert "의식을 봉합" in validated.narrative
    assert "실패" not in validated.narrative
