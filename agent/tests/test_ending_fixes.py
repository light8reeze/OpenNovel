from app.game.models import ContentBundle, Location, Npc, QuestDefinition, QuestStageDefinition, ThemePack, ThemeVictoryPath, WorldState, initial_state
from app.prompts.narrative_builder import build_narrative_prompts, _outcome_block
from app.retrieval.schemas import RetrievalContext
from app.schemas.common import Action, ActionType, EngineResult, SceneContext, StateSummary
from app.schemas.multi_agent import WorldBlueprint, WorldLocation
from app.schemas.narrative import NarrativeRequest
from app.services.validator import RuleValidator


def test_ending_outcome_block_contains_directive() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(turn=6, location_id="sealed_well", hp=88, gold=15, story_arc_stage=4),
        scene_context=SceneContext(location_name="봉인된 우물"),
        engine_result=EngineResult(
            success=True,
            message_code="OBJECTIVE_COMPLETED",
            location_changed=False,
            quest_stage_changed=False,
            ending_reached="sealed",
            details=["victory:sealed"],
        ),
        allowed_choices=[],
    )

    outcome_block = _outcome_block(request)

    assert "⚠️ ENDING DIRECTIVE:" in outcome_block
    assert "엔딩 'sealed'" in outcome_block
    assert "미완료 표현 금지" in outcome_block


def test_validator_clears_choices_on_ending() -> None:
    validator = _validator_with_ending_theme()
    blueprint = WorldBlueprint(
        id="ending_test_world",
        title="엔딩 테스트",
        world_summary="엔딩 선택지 정리를 검증한다.",
        tone="긴장",
        core_conflict="마지막 의식을 마무리한다.",
        player_goal="의식을 끝낸다.",
        opening_hook="우물 앞에 선다.",
        starting_location_id="sealed_well",
        locations=[WorldLocation(id="sealed_well", label="봉인된 우물", connections=[])],
        theme_id="ending_theme",
    )
    state = initial_state(seed=11)
    state.player.location_id = "sealed_well"
    state.world = WorldState(time="night", theme_id="ending_theme")
    state.quests.story_arc.stage = 2

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.USE_ITEM, target="sealed_well", raw_input="우물을 봉인한다"),
        proposal_summary="의식이 마침내 닫힌다.",
        proposal_patch={},
        proposal_choices=["우물을 다시 조사한다", "마을로 돌아간다"],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.engine_result.message_code == "OBJECTIVE_COMPLETED"
    assert result.allowed_choices == []
    assert "ending_reached_no_choices" in result.validation_flags


def test_narrative_prompt_shows_no_choices_on_ending() -> None:
    request = NarrativeRequest(
        state_summary=StateSummary(turn=6, location_id="sealed_well", hp=88, gold=15, story_arc_stage=4),
        scene_context=SceneContext(location_name="봉인된 우물"),
        engine_result=EngineResult(
            success=True,
            message_code="OBJECTIVE_COMPLETED",
            location_changed=False,
            quest_stage_changed=False,
            ending_reached="sealed",
            details=["victory:sealed"],
        ),
        allowed_choices=["우물을 다시 조사한다"],
    )

    _, user_prompt = build_narrative_prompts("turn", request, RetrievalContext())

    assert "Allowed Choices:\n- (게임 종료 - 선택지 없음)" in user_prompt


def _validator_with_ending_theme() -> RuleValidator:
    content = ContentBundle(
        locations=[Location(id="sealed_well", name="봉인된 우물", description="마지막 의식의 중심이다.")],
        npcs=[Npc(id="warden", name="수문장", location_id="sealed_well", role="guide")],
        story_arc=QuestDefinition(id="ending_arc", title="엔딩", stages=[QuestStageDefinition(stage=0, summary="시작")]),
        theme_packs=[
            ThemePack(
                id="ending_theme",
                title_prefix="엔딩",
                summary_prefix="엔딩",
                tone="긴장",
                opening_hook="우물 앞에 선다.",
                victory_paths=[
                    ThemeVictoryPath(
                        id="sealed",
                        label="봉인 의식",
                        required_action="USE_ITEM",
                        required_location_index=0,
                        min_stage=2,
                        details=["ritual_complete"],
                    )
                ],
            )
        ],
    )
    return RuleValidator(content)
