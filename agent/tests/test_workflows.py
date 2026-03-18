from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["intender"]["provider"]
    assert payload["narrator"]["provider"]
    assert payload["vectorStore"]["provider"] == "chroma"
    assert payload["debugUiEnabled"] is True


def test_intent_validation_returns_action() -> None:
    response = client.post(
        "/intent/validate",
        json={
            "player_input": "회랑으로 이동한다",
            "allowed_actions": ["MOVE", "INVESTIGATE"],
            "state_summary": {
                "turn": 0,
                "location_id": "ruins_entrance",
                "hp": 100,
                "gold": 15,
                "sunken_ruins_stage": 0,
                "player_flags": [],
            },
            "scene_context": {
                "location_name": "Sunken Ruins Entrance",
                "npcs_in_scene": ["caretaker"],
                "visible_targets": ["hall", "caretaker"],
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
                "location_id": "collapsed_hall",
                "hp": 100,
                "gold": 15,
                "sunken_ruins_stage": 2,
                "player_flags": [],
            },
            "scene_context": {
                "location_name": "Collapsed Hall",
                "npcs_in_scene": [],
                "visible_targets": ["trap_room", "ruins_entrance"],
            },
            "engine_result": {
                "success": True,
                "message_code": "NOTHING_FOUND",
                "location_changed": False,
                "quest_stage_changed": False,
                "ending_reached": None,
                "details": ["empty_search"],
            },
            "allowed_choices": [
                "주변을 조사한다",
                "함정방으로 이동한다",
                "입구로 돌아간다",
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["choices"]) >= 2
    assert isinstance(payload["retrieved_document_ids"], list)
