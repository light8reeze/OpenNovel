from app.game.models import ContentBundle, Location, Npc, QuestDefinition, QuestStageDefinition, initial_state
from app.schemas.common import Action, ActionType
from app.schemas.multi_agent import NpcBehavior, NpcEvent, WorldBlueprint, WorldLocation, WorldNpc
from app.services.validator import RuleValidator


def test_npc_behavior_and_event_models_import_correctly() -> None:
    behavior = NpcBehavior(
        trigger="turn_start",
        condition="turn >= 2",
        action="watch_silently",
        cooldown_turns=1,
        message="누군가 지켜본다.",
    )
    event = NpcEvent(
        npc_id="caretaker",
        npc_label="관리인",
        action="watch_silently",
        message="누군가 지켜본다.",
    )

    assert behavior.trigger == "turn_start"
    assert event.npc_id == "caretaker"


def test_npc_event_triggers_on_high_affinity() -> None:
    validator = _validator()
    blueprint = _blueprint(
        WorldNpc(
            id="caretaker",
            label="관리인",
            home_location_id="entrance",
            personality="신중하다.",
            behaviors=[
                NpcBehavior(
                    trigger="affinity_threshold",
                    condition="affinity >= 7",
                    action="offer_help",
                    cooldown_turns=2,
                    message="관리인이 잠긴 문을 여는 순서를 알려 준다.",
                )
            ],
        )
    )
    state = initial_state(seed=1)
    state.player.location_id = "entrance"
    state.relations.npc_affinity["caretaker"] = 8

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.REST, raw_input="숨을 고른다"),
        proposal_summary="잠시 멈춘다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert any(detail.startswith("npc_event:caretaker:offer_help:") for detail in result.engine_result.details)


def test_npc_event_skipped_when_condition_not_met() -> None:
    validator = _validator()
    blueprint = _blueprint(
        WorldNpc(
            id="caretaker",
            label="관리인",
            home_location_id="entrance",
            behaviors=[
                NpcBehavior(
                    trigger="affinity_threshold",
                    condition="affinity >= 7",
                    action="offer_help",
                    cooldown_turns=2,
                    message="관리인이 도움을 제안한다.",
                )
            ],
        )
    )
    state = initial_state(seed=2)
    state.player.location_id = "entrance"
    state.relations.npc_affinity["caretaker"] = 6

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.REST, raw_input="숨을 고른다"),
        proposal_summary="잠시 멈춘다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert not any(detail.startswith("npc_event:caretaker:offer_help:") for detail in result.engine_result.details)


def test_npc_event_triggers_on_player_enters() -> None:
    validator = _validator()
    blueprint = _blueprint(
        WorldNpc(
            id="watcher",
            label="감시자",
            home_location_id="hall",
            behaviors=[
                NpcBehavior(
                    trigger="player_enters",
                    condition="turn >= 1",
                    action="greet_with_warning",
                    cooldown_turns=1,
                    message="감시자가 회랑의 공기가 이미 누군가에게 흔들렸다고 경고한다.",
                )
            ],
        )
    )
    state = initial_state(seed=3)
    state.player.location_id = "entrance"

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.MOVE, target="회랑", raw_input="회랑으로 이동한다"),
        proposal_summary="회랑으로 향한다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.state.player.location_id == "hall"
    assert any(detail.startswith("npc_event:watcher:greet_with_warning:") for detail in result.engine_result.details)


def test_npc_event_respects_cooldown() -> None:
    validator = _validator()
    blueprint = _blueprint(
        WorldNpc(
            id="caretaker",
            label="관리인",
            home_location_id="entrance",
            behaviors=[
                NpcBehavior(
                    trigger="turn_start",
                    condition="turn >= 1",
                    action="watch_silently",
                    cooldown_turns=2,
                    message="관리인이 침묵 속에서 반응을 살핀다.",
                )
            ],
        )
    )
    state = initial_state(seed=4)
    state.player.location_id = "entrance"

    first = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.REST, raw_input="숨을 고른다"),
        proposal_summary="잠시 멈춘다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )
    second = validator.validate_transition(
        state=first.state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.REST, raw_input="다시 숨을 고른다"),
        proposal_summary="잠시 멈춘다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert any(detail.startswith("npc_event:caretaker:watch_silently:") for detail in first.engine_result.details)
    assert not any(detail.startswith("npc_event:caretaker:watch_silently:") for detail in second.engine_result.details)


def test_npc_event_added_to_engine_result_details() -> None:
    validator = _validator()
    blueprint = _blueprint(
        WorldNpc(
            id="caretaker",
            label="관리인",
            home_location_id="entrance",
            behaviors=[
                NpcBehavior(
                    trigger="turn_start",
                    condition="turn == 1",
                    action="reveal_secret",
                    cooldown_turns=0,
                    message="관리인이 벽 뒤 빈 공간을 알려 준다.",
                )
            ],
        )
    )
    state = initial_state(seed=5)
    state.player.location_id = "entrance"

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.REST, raw_input="숨을 고른다"),
        proposal_summary="잠시 멈춘다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.engine_result.details[0] == "REST"
    assert "progress:stalled" in result.engine_result.details
    assert any(detail.startswith("npc_event:caretaker:reveal_secret:") for detail in result.engine_result.details)


def _validator() -> RuleValidator:
    return RuleValidator(
        ContentBundle(
            locations=[
                Location(id="entrance", name="입구", description="시작 지점"),
                Location(id="hall", name="회랑", description="다음 구역"),
            ],
            npcs=[Npc(id="caretaker", name="관리인", location_id="entrance", role="guide")],
            story_arc=QuestDefinition(id="arc", title="arc", stages=[QuestStageDefinition(stage=0, summary="start")]),
            theme_packs=[],
        )
    )


def _blueprint(npc: WorldNpc) -> WorldBlueprint:
    return WorldBlueprint(
        id="npc_autonomy_test",
        title="NPC 자율 행동 테스트",
        world_summary="NPC 자율 이벤트를 검증한다.",
        tone="긴장",
        core_conflict="NPC 반응을 확인한다.",
        player_goal="NPC 이벤트를 확인한다.",
        opening_hook="입구에 선다.",
        starting_location_id="entrance",
        locations=[
            WorldLocation(id="entrance", label="입구", connections=["hall"]),
            WorldLocation(id="hall", label="회랑", connections=["entrance"]),
        ],
        npcs=[npc],
    )
