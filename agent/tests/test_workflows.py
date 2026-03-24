from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["storyAgent"]["provider"]
    assert payload["intender"]["provider"]
    assert payload["narrator"]["provider"]
    assert payload["worldBuilder"]["provider"]
    assert payload["stateManager"]["provider"]
    assert payload["validator"]["type"] == "deterministic"
    assert payload["vectorStore"]["provider"] == "chroma"
    assert payload["storySetups"]["count"] == 3
    assert payload["debugUiEnabled"] is True


def test_intent_validation_returns_action() -> None:
    response = client.post(
        "/intent/validate",
        json={
            "player_input": "안개 골목으로 이동한다",
            "allowed_actions": ["MOVE", "INVESTIGATE"],
            "state_summary": {
                "turn": 0,
                "location_id": "harbor_dock",
                "hp": 100,
                "gold": 15,
                "story_arc_stage": 0,
                "player_flags": [],
            },
            "scene_context": {
                "location_name": "젖은 부두",
                "npcs_in_scene": ["항구 경비"],
                "visible_targets": ["안개 골목", "항구 경비"],
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"]["action_type"] == "MOVE"
    assert isinstance(payload["retrieved_document_ids"], list)


def test_turn_narrative_returns_allowed_choices() -> None:
    response = client.post(
        "/narrative/turn",
        json={
            "state_summary": {
                "turn": 1,
                "location_id": "fog_alley",
                "hp": 100,
                "gold": 15,
                "story_arc_stage": 2,
                "player_flags": [],
            },
            "scene_context": {
                "location_name": "안개 골목",
                "npcs_in_scene": [],
                "visible_targets": ["밀수 창고", "젖은 부두"],
            },
            "engine_result": {
                "success": True,
                "message_code": "INVESTIGATE_PROGRESS",
                "location_changed": False,
                "quest_stage_changed": True,
                "ending_reached": None,
                "details": ["found_smuggling_mark"],
            },
            "allowed_choices": [
                "주변을 조사한다",
                "밀수 창고로 이동한다",
                "젖은 부두로 돌아간다",
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["choices"]) >= 2
    assert isinstance(payload["retrieved_document_ids"], list)
