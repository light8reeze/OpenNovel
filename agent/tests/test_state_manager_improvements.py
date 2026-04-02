from app.game.models import GameState, MetaState, ObjectiveState, PlayerState, QuestProgress, QuestState, RelationsState, WorldState
from app.prompts.state_manager import build_state_proposal_prompts
from app.schemas.common import Action, ActionType
from app.schemas.multi_agent import StoryTransitionProposalRequest, WorldBlueprint, WorldLocation, WorldNpc


def _request() -> StoryTransitionProposalRequest:
    return StoryTransitionProposalRequest(
        state=GameState(
            meta=MetaState(turn=6, seed=12345),
            player=PlayerState(hp=92, gold=15, location_id="sanctum"),
            world=WorldState(time="night", theme_id="sunken_ruins"),
            quests=QuestState(story_arc=QuestProgress(stage=3)),
            objective=ObjectiveState(),
            relations=RelationsState(),
        ),
        world_blueprint=WorldBlueprint(
            id="sunken_ruins_world",
            title="침수 유적",
            world_summary="침수된 폐허 중심에서 오래된 봉인이 흔들리고 있다.",
            tone="축축하고 음산한 탐사",
            core_conflict="유적 중심의 봉인과 유물 인양 욕망이 충돌한다.",
            player_goal="유적 깊은 곳의 진실을 파악한다.",
            opening_hook="젖은 계단 아래에서 오래된 수문이 다시 움직인다.",
            locations=[
                WorldLocation(
                    id="entrance",
                    label="폐허 입구",
                    connections=["hall"],
                    investigation_hooks=["젖은 석문"],
                ),
                WorldLocation(
                    id="hall",
                    label="잠긴 회랑",
                    connections=["entrance", "sanctum"],
                    investigation_hooks=["잠수 흔적"],
                ),
                WorldLocation(
                    id="sanctum",
                    label="깊은 성소",
                    connections=["hall"],
                    investigation_hooks=["가라앉은 제단", "수문 흔적"],
                ),
            ],
            npcs=[
                WorldNpc(
                    id="oracle",
                    label="조수의 예언자",
                    home_location_id="sanctum",
                    role="keeper",
                    interaction_hint="유적 중심의 대가를 설명한다.",
                )
            ],
            theme_id="sunken_ruins",
        ),
        discovery_log=["입구의 물결이 거꾸로 흐른다."],
        history=[],
        intent=Action(
            action_type=ActionType.INVESTIGATE,
            target="sanctum",
            raw_input="깊은 성소를 조사한다",
        ),
    )


def test_victory_conditions_in_prompt() -> None:
    _, user_prompt = build_state_proposal_prompts(_request())

    assert '"victory_conditions_summary":' in user_prompt
    assert '"victory_paths": [' in user_prompt
    assert '"path_id": "recovered"' in user_prompt
    assert '"required_action": "INVESTIGATE"' in user_prompt
    assert '"required_location": "깊은 성소"' in user_prompt
    assert '"min_stage": 3' in user_prompt
    assert "If victory conditions are met (correct action + location + stage), reflect completion tone in scene_summary." in user_prompt


def test_choice_candidates_use_available_actions() -> None:
    _, user_prompt = build_state_proposal_prompts(_request())

    assert '"allowed_actions": [' in user_prompt
    assert '"INVESTIGATE"' in user_prompt
    assert '"TALK"' in user_prompt
    assert '"MOVE"' in user_prompt
    assert '"USE_ITEM"' in user_prompt
    assert '"REST"' in user_prompt
    assert '"location_connections": {' in user_prompt
    assert '"connected_locations": [' in user_prompt
    assert '"label": "잠긴 회랑"' in user_prompt
    assert '"available_actions": [' in user_prompt
    assert "Base every choice candidate on the Available Actions section." in user_prompt
    assert "MOVE choices must only use connected_locations from location_connections." in user_prompt
    assert "INVESTIGATE choices should reflect current_location_hooks when hooks remain." in user_prompt
    assert '"hooks": [' in user_prompt
    assert '"가라앉은 제단"' in user_prompt
