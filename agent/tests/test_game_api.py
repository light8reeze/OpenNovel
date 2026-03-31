from fastapi.testclient import TestClient

from app.game.models import initial_state
from app.main import app
from app.runtime import get_runtime
from app.schemas.common import Action, ActionType
from app.schemas.multi_agent import WorldBlueprint, WorldLocation
from app.schemas.story_setup import StorySetup


client = TestClient(app)


def test_start_game_returns_rust_compatible_shape() -> None:
    response = client.post("/game/start", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["sessionId"].startswith("session-")
    assert payload["state"]["meta"]["turn"] == 0
    assert payload["storySetupId"]
    assert payload["choices"] == []
    assert payload["state"]["world"]["theme_id"]
    assert payload["state"]["objective"]["status"] == "in_progress"
    assert payload["state"]["objective"]["victory_path"] is None


def test_story_setups_returns_three_presets() -> None:
    response = client.get("/story-setups")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"llm", "fallback"}
    assert len(payload["presets"]) == 3
    assert all(preset["id"] for preset in payload["presets"])


def test_start_game_uses_requested_story_setup_and_persists_it() -> None:
    presets = client.get("/story-setups").json()["presets"]
    selected_id = presets[1]["id"]
    response = client.post("/game/start", json={"storySetupId": selected_id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["storySetupId"] == selected_id

    state_response = client.get("/game/state", params={"sessionId": payload["sessionId"]})
    assert state_response.status_code == 200
    assert state_response.json()["storySetupId"] == selected_id


def test_start_game_opening_and_choices_reflect_selected_story_setup() -> None:
    presets = client.get("/story-setups").json()["presets"]
    selected = presets[1]
    response = client.post("/game/start", json={"storySetupId": selected["id"]})
    assert response.status_code == 200
    payload = response.json()
    assert selected["title"] in payload["narrative"]
    assert payload["choices"] == []


def test_theme_pack_preserves_story_setup_world_identity() -> None:
    presets = client.get("/story-setups").json()["presets"]
    selected = presets[0]
    response = client.post("/game/start", json={"storySetupId": selected["id"]})
    assert response.status_code == 200
    payload = response.json()

    opening_log = client.get("/debug/turn-log", params={"sessionId": payload["sessionId"], "turn": 0})
    assert opening_log.status_code == 200
    blueprint = opening_log.json()["worldBuildResponse"]["blueprint"]

    assert blueprint["title"] == selected["title"]
    assert blueprint["world_summary"] == selected["world_summary"]
    assert blueprint["opening_hook"] == selected["opening_hook"]
    assert blueprint["theme_id"]


def test_theme_pack_selection_prefers_setup_compatible_worlds() -> None:
    runtime = get_runtime()
    story_setup = next(setup for setup in runtime.story_setups if setup.id == "sunken_ruins")
    blueprint = WorldBlueprint(
        id=story_setup.id,
        title=story_setup.title,
        world_summary=story_setup.world_summary,
        tone=story_setup.tone,
        core_conflict=story_setup.player_goal,
        player_goal=story_setup.player_goal,
        opening_hook=story_setup.opening_hook,
        starting_location_id="entrance",
        locations=[
            WorldLocation(id="entrance", label="폐허 입구", connections=["depth"], investigation_hooks=["젖은 석문 틈"]),
            WorldLocation(id="depth", label="침수 성소", connections=["entrance"], investigation_hooks=["수문 흔적"]),
        ],
    )

    selected = runtime.game._select_theme_pack(story_setup, blueprint, seed=7)

    assert selected is not None
    assert selected.id == "sunken_ruins"


def test_world_builder_fallback_seed_preserves_setup_genre() -> None:
    runtime = get_runtime()
    builder = runtime.world_builder

    temple_labels, temple_npc = builder._fallback_seed(
        StorySetup(
            id="abandoned_temple",
            title="버려진 사찰의 비밀",
            world_summary="버려진 사찰",
            tone="미스터리",
            player_goal="사찰의 비밀을 밝힌다.",
            opening_hook="비밀이 깨어난다.",
            style_guardrails=["설정의 일관성을 유지한다", "과장된 장르 혼합을 피한다"],
        )
    )
    royal_labels, royal_npc = builder._fallback_seed(
        StorySetup(
            id="royal_conspiracy",
            title="궁중 암투의 그림자",
            world_summary="궁궐의 음모",
            tone="정치 스릴러",
            player_goal="궁중 암투의 진실을 밝힌다.",
            opening_hook="침전 앞에 그림자가 드리운다.",
            style_guardrails=["설정의 일관성을 유지한다", "과장된 장르 혼합을 피한다"],
        )
    )

    assert temple_labels[0] == "낡은 대웅전"
    assert temple_npc == "노승"
    assert royal_labels[0] == "침전 앞 회랑"
    assert royal_npc == "상궁"


def test_game_choices_returns_current_suggestions_only_on_request() -> None:
    start = client.post("/game/start", json={"storySetupId": "sunken_ruins"}).json()
    assert start["choices"] == []

    choices_response = client.get("/game/choices", params={"sessionId": start["sessionId"]})
    assert choices_response.status_code == 200
    choices_payload = choices_response.json()
    assert choices_payload["sessionId"] == start["sessionId"]
    assert len(choices_payload["choices"]) >= 2
    assert all("(" not in choice and ")" not in choice for choice in choices_payload["choices"])
    assert all(
        "collapsed_hall" not in choice and "trap_chamber" not in choice and "caretaker" not in choice
        for choice in choices_payload["choices"]
    )
    assert any("조사" in choice for choice in choices_payload["choices"])
    assert any("이동" in choice for choice in choices_payload["choices"])


def test_start_game_falls_back_to_default_story_setup_for_unknown_id() -> None:
    presets = client.get("/story-setups").json()["presets"]
    default_id = presets[0]["id"]
    response = client.post("/game/start", json={"storySetupId": "missing-setup"})
    assert response.status_code == 200
    assert response.json()["storySetupId"] == default_id


def test_game_state_returns_404_for_unknown_session() -> None:
    response = client.get("/game/state", params={"sessionId": "missing-session"})
    assert response.status_code == 404
    assert response.json()["detail"] == "session not found"


def test_game_action_rejects_ambiguous_input() -> None:
    start = client.post("/game/start", json={}).json()
    response = client.post(
        "/game/action",
        json={
            "sessionId": start["sessionId"],
            "inputText": "주변을 조사한다",
            "choiceText": "창고로 이동한다",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "inputText and choiceText cannot both be set"


def test_story_agent_progresses_session_without_engine() -> None:
    start = client.post("/game/start", json={}).json()
    session_id = start["sessionId"]
    message_codes: list[str] = []

    for step in [
        "주변을 조사한다",
        "회랑으로 이동한다",
        "주변을 조사한다",
        "함정방으로 이동한다",
        "주변을 조사한다",
        "성소로 이동한다",
        "주변을 조사한다",
        "주변을 조사한다",
        "함정방으로 이동한다",
        "회랑으로 돌아간다",
        "입구로 돌아간다",
        "주변을 조사한다",
    ]:
        response = client.post("/game/action", json={"sessionId": session_id, "inputText": step})
        assert response.status_code == 200
        payload = response.json()
        assert payload["choices"] == []
        message_codes.append(payload["engineResult"]["message_code"])
    assert all(code for code in message_codes)
    final_state = payload["state"]
    assert final_state["meta"]["turn"] == len(message_codes)
    assert final_state["quests"]["story_arc"]["stage"] >= 1
    assert final_state["player"]["gold"] == 15
    assert payload["engineResult"]["ending_reached"] in {None, "recovered", "sealed", "bargained"}


def test_cumulative_style_scores_activate_tags() -> None:
    start = client.post("/game/start", json={}).json()
    session_id = start["sessionId"]

    for _ in range(2):
        response = client.post("/game/action", json={"sessionId": session_id, "inputText": "주변을 조사한다"})
        assert response.status_code == 200

    state = response.json()["state"]
    assert state["player"]["style_scores"]["curious"] >= 4
    assert "curious" in state["player"]["style_tags"]


def test_reaching_final_location_can_complete_objective_with_explicit_victory_path() -> None:
    start = client.post("/game/start", json={}).json()
    session_id = start["sessionId"]

    opening_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 0}).json()
    locations = opening_log["worldBuildResponse"]["blueprint"]["locations"]

    for location in locations[1:]:
        choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
        move_choice = next(choice for choice in choices if location["label"] in choice and "이동" in choice)
        move_response = client.post("/game/action", json={"sessionId": session_id, "choiceText": move_choice})
        assert move_response.status_code == 200

    action = client.post("/game/action", json={"sessionId": session_id, "inputText": "주변을 조사한다"})
    assert action.status_code == 200
    payload = action.json()
    assert payload["engineResult"]["message_code"] == "OBJECTIVE_COMPLETED"
    assert payload["engineResult"]["ending_reached"] == "recovered"
    assert payload["state"]["objective"]["status"] == "completed"
    assert payload["state"]["objective"]["victory_path"] == "recovered"


def test_reaching_final_location_can_complete_objective_with_talk_path() -> None:
    start = client.post("/game/start", json={}).json()
    session_id = start["sessionId"]

    opening_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 0}).json()
    locations = opening_log["worldBuildResponse"]["blueprint"]["locations"]

    for location in locations[1:]:
        choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
        move_choice = next(choice for choice in choices if location["label"] in choice and "이동" in choice)
        move_response = client.post("/game/action", json={"sessionId": session_id, "choiceText": move_choice})
        assert move_response.status_code == 200

    choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
    talk_choice = next(choice for choice in choices if "대화" in choice)
    action = client.post("/game/action", json={"sessionId": session_id, "choiceText": talk_choice})
    assert action.status_code == 200
    payload = action.json()
    assert payload["engineResult"]["message_code"] == "OBJECTIVE_COMPLETED"
    assert payload["engineResult"]["ending_reached"] == "bargained"
    assert payload["state"]["objective"]["status"] == "completed"
    assert payload["state"]["objective"]["victory_path"] == "bargained"


def test_reaching_final_location_can_complete_objective_with_sealed_path_choice() -> None:
    start = client.post("/game/start", json={}).json()
    session_id = start["sessionId"]

    opening_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 0}).json()
    locations = opening_log["worldBuildResponse"]["blueprint"]["locations"]

    for location in locations[1:]:
        choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
        move_choice = next(choice for choice in choices if location["label"] in choice and "이동" in choice)
        move_response = client.post("/game/action", json={"sessionId": session_id, "choiceText": move_choice})
        assert move_response.status_code == 200

    choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
    seal_choice = next(choice for choice in choices if "봉인" in choice)
    action = client.post("/game/action", json={"sessionId": session_id, "choiceText": seal_choice})
    assert action.status_code == 200
    payload = action.json()
    assert payload["engineResult"]["message_code"] == "OBJECTIVE_COMPLETED"
    assert payload["engineResult"]["ending_reached"] == "sealed"
    assert payload["state"]["objective"]["status"] == "completed"
    assert payload["state"]["objective"]["victory_path"] == "sealed"


def test_repeated_investigate_eventually_stalls_in_same_location() -> None:
    presets = client.get("/story-setups").json()["presets"]
    start = client.post("/game/start", json={"storySetupId": presets[0]["id"]}).json()
    session_id = start["sessionId"]

    progress_kinds: list[str] = []
    stages: list[int] = []

    for turn in range(1, 5):
        choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
        investigate_choice = next((choice for choice in choices if "조사" in choice), "주변을 조사한다")
        payload = client.post("/game/action", json={"sessionId": session_id, "choiceText": investigate_choice}).json()
        stages.append(payload["state"]["quests"]["story_arc"]["stage"])
        bundle = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": turn}).json()
        progress_kinds.append(bundle["validationResponse"]["progress_kind"])

    assert "investigate" in progress_kinds
    assert "stalled" in progress_kinds
    assert stages[-1] <= stages[0] + 1


def test_talk_and_move_create_different_progress_kinds() -> None:
    presets = client.get("/story-setups").json()["presets"]
    start = client.post("/game/start", json={"storySetupId": presets[0]["id"]}).json()
    session_id = start["sessionId"]

    choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
    talk_choice = next((choice for choice in choices if "대화" in choice), None)
    move_choice = next((choice for choice in choices if "이동" in choice), None)

    if talk_choice:
        client.post("/game/action", json={"sessionId": session_id, "choiceText": talk_choice})
        talk_bundle = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 1}).json()
        assert talk_bundle["validationResponse"]["progress_kind"] in {"talk", "stalled"}

    if move_choice:
        client.post("/game/action", json={"sessionId": session_id, "choiceText": move_choice})
        move_turn = 2 if talk_choice else 1
        move_bundle = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": move_turn}).json()
        assert move_bundle["validationResponse"]["progress_kind"] in {"move", "reposition", "stalled"}

    if talk_choice and move_choice:
        assert talk_bundle["validationResponse"]["progress_kind"] != move_bundle["validationResponse"]["progress_kind"]


def test_choice_text_uses_exact_visible_move_choice_without_reinterpreting_target() -> None:
    presets = client.get("/story-setups").json()["presets"]
    start = client.post("/game/start", json={"storySetupId": presets[0]["id"]}).json()
    session_id = start["sessionId"]

    opening_choices = client.get("/game/choices", params={"sessionId": session_id}).json()["choices"]
    move_choice = next(choice for choice in opening_choices if "이동" in choice)
    move_payload = client.post("/game/action", json={"sessionId": session_id, "choiceText": move_choice}).json()

    assert move_payload["engineResult"]["message_code"] == "MOVE_OK"
    assert move_payload["engineResult"]["location_changed"] is True

    move_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 1}).json()
    opening_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 0}).json()
    assert move_log["intentResponse"]["source"] == "choice_match"
    assert move_log["intentResponse"]["action"]["action_type"] == "MOVE"
    target_label = move_log["intentResponse"]["action"]["target"]
    assert isinstance(target_label, str) and target_label
    assert target_label in move_choice

    world_locations = opening_log["worldBuildResponse"]["blueprint"]["locations"]
    target_location_id = next(location["id"] for location in world_locations if location["label"] == target_label)
    assert move_log["gameResponse"]["state"]["player"]["location_id"] == target_location_id
    assert target_label in move_log["validationResponse"]["scene_summary"]


def test_validator_uses_validated_move_summary_over_llm_proposal() -> None:
    runtime = get_runtime()
    validator = runtime.validator
    blueprint = WorldBlueprint(
        id="sunken_ruins",
        title="가라앉은 폐허",
        world_summary="침수 유적",
        tone="음산한 탐사",
        core_conflict="깊은 곳의 유물을 회수한다.",
        player_goal="유물을 회수한다.",
        opening_hook="석문이 열린다.",
        starting_location_id="entrance",
        locations=[
            WorldLocation(id="entrance", label="폐허 입구", connections=["sanctum"], investigation_hooks=["젖은 발자국"]),
            WorldLocation(id="sanctum", label="깊은 성소", connections=["entrance"], investigation_hooks=["잠긴 제단"]),
        ],
    )
    state = initial_state(seed=1)
    state.player.location_id = "entrance"

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.MOVE, target="깊은 성소", raw_input="깊은 성소로 이동한다"),
        proposal_summary="폐허 입구에서 머뭇거리며 주위를 본다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.state.player.location_id == "sanctum"
    assert "깊은 성소" in result.scene_summary
    assert "폐허 입구" not in result.scene_summary
    assert result.progress_kind == "move"
    assert "validator_ignored_move_patch" not in result.validation_flags


def test_validator_ignores_move_location_patch_and_uses_intent_target() -> None:
    runtime = get_runtime()
    validator = runtime.validator
    blueprint = WorldBlueprint(
        id="sunken_ruins",
        title="가라앉은 폐허",
        world_summary="침수 유적",
        tone="음산한 탐사",
        core_conflict="깊은 곳의 유물을 회수한다.",
        player_goal="유물을 회수한다.",
        opening_hook="석문이 열린다.",
        starting_location_id="entrance",
        locations=[
            WorldLocation(id="entrance", label="폐허 입구", connections=["hall", "sanctum"], investigation_hooks=["젖은 발자국"]),
            WorldLocation(id="hall", label="무너진 회랑", connections=["entrance"], investigation_hooks=["무너진 석상"]),
            WorldLocation(id="sanctum", label="깊은 성소", connections=["entrance"], investigation_hooks=["잠긴 제단"]),
        ],
    )
    state = initial_state(seed=1)
    state.player.location_id = "entrance"

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.MOVE, target="깊은 성소", raw_input="깊은 성소로 이동한다"),
        proposal_summary="무너진 회랑 쪽으로 몸을 돌린다.",
        proposal_patch={"player": {"location_id": "무너진 회랑"}},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.state.player.location_id == "sanctum"
    assert result.progress_kind == "move"
    assert "validator_ignored_move_patch" in result.validation_flags


def test_validator_can_progress_finale_after_hooks_are_exhausted() -> None:
    runtime = get_runtime()
    validator = runtime.validator
    blueprint = WorldBlueprint(
        id="sunken_ruins",
        title="가라앉은 폐허",
        world_summary="침수 유적",
        tone="음산한 탐사",
        core_conflict="깊은 곳의 유물을 회수한다.",
        player_goal="유물을 회수한다.",
        opening_hook="석문이 열린다.",
        starting_location_id="entrance",
        locations=[
            WorldLocation(id="entrance", label="폐허 입구", connections=["sanctum"], investigation_hooks=["젖은 석문"]),
            WorldLocation(id="sanctum", label="깊은 성소", connections=["entrance"], investigation_hooks=[]),
        ],
        theme_id="sunken_ruins",
        theme_rules=["조사는 숨겨진 진실을 드러낸다."],
    )
    state = initial_state(seed=1)
    state.player.location_id = "sanctum"
    state.world.theme_id = "sunken_ruins"
    state.world.theme_rules = ["조사는 숨겨진 진실을 드러낸다."]
    state.quests.story_arc.stage = 2

    result = validator.validate_transition(
        state=state,
        world_blueprint=blueprint,
        discovery_log=[],
        intent=Action(action_type=ActionType.INVESTIGATE, target="깊은 성소", raw_input="깊은 성소를 더 조사한다"),
        proposal_summary="더는 볼 것이 없는 듯하다.",
        proposal_patch={},
        proposal_choices=[],
        proposed_facts=[],
        risk_tags=[],
    )

    assert result.progress_kind == "investigate"
    assert result.state.quests.story_arc.stage == 3
    assert result.engine_result.message_code == "OBJECTIVE_COMPLETED"
    assert result.state.objective.victory_path == "recovered"


def test_investigate_choice_does_not_duplicate_location_prefix() -> None:
    runtime = get_runtime()
    validator = runtime.validator

    choice = validator._investigate_choice("폐허 입구", "폐허 입구에서 수상한 흔적을 발견할 수 있다.")

    assert choice == "폐허 입구에서 수상한 흔적을 발견할 수 있다.를 조사한다"


def test_frontend_shell_is_served_from_agent() -> None:
    index = client.get("/")
    script = client.get("/frontend/app.js")
    assert index.status_code == 200
    assert "OpenNovel MVP" in index.text
    assert script.status_code == 200
    assert "renderGraph" in script.text


def test_debug_turn_log_returns_opening_and_turn_bundles() -> None:
    start = client.post("/game/start", json={}).json()
    session_id = start["sessionId"]

    opening_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 0})
    assert opening_log.status_code == 200
    opening_payload = opening_log.json()
    assert opening_payload["found"] is True
    assert opening_payload["gameResponse"]["sessionId"] == session_id
    assert opening_payload["worldBuildResponse"]["blueprint"]["title"]
    assert opening_payload["validationResponse"]["state"]["meta"]["turn"] == 0
    assert opening_payload["narrativeResponse"]["narrative"]

    action = client.post(
        "/game/action",
        json={"sessionId": session_id, "inputText": "회랑으로 이동한다"},
    ).json()
    turn_log = client.get("/debug/turn-log", params={"sessionId": session_id, "turn": 1})
    assert turn_log.status_code == 200
    turn_payload = turn_log.json()
    assert turn_payload["found"] is True
    assert turn_payload["gameResponse"]["engineResult"]["message_code"] == action["engineResult"]["message_code"]
    assert turn_payload["intentResponse"]["action"]["action_type"] == "MOVE"
    assert turn_payload["stateProposalResponse"]["scene_summary"]
    assert turn_payload["validationResponse"]["engine_result"]["message_code"] == action["engineResult"]["message_code"]
    assert turn_payload["narrativeResponse"]["narrative"]


def test_debug_turn_log_returns_empty_bundle_for_missing_turn() -> None:
    response = client.get("/debug/turn-log", params={"sessionId": "missing-session", "turn": 99})
    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is False
    assert payload["gameRequest"] is None
