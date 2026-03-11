from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["provider"] == "mock"


def test_intent_validation_returns_action() -> None:
    response = client.post(
        "/intent/validate",
        json={
            "player_input": "창고로 이동한다",
            "allowed_actions": ["MOVE", "INVESTIGATE"],
            "state_summary": {
                "turn": 0,
                "location_id": "village_square",
                "hp": 100,
                "gold": 20,
                "murder_case_stage": 0,
                "player_flags": [],
            },
            "scene_context": {
                "location_name": "Village Square",
                "npcs_in_scene": ["aria"],
                "visible_targets": ["warehouse", "aria"],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["action"]["action_type"] == "MOVE"


def test_turn_narrative_returns_allowed_choices() -> None:
    response = client.post(
        "/narrative/turn",
        json={
            "state_summary": {
                "turn": 1,
                "location_id": "village_warehouse",
                "hp": 100,
                "gold": 20,
                "murder_case_stage": 1,
                "player_flags": [],
            },
            "scene_context": {
                "location_name": "Village Warehouse",
                "npcs_in_scene": ["aria"],
                "visible_targets": ["aria", "village_square"],
            },
            "engine_result": {
                "success": True,
                "message_code": "BLOODY_CLOTH_FOUND",
                "location_changed": False,
                "quest_stage_changed": True,
                "ending_reached": None,
                "details": ["bloody_cloth"],
            },
            "allowed_choices": [
                "주변을 조사한다",
                "아리아와 대화한다",
                "광장으로 이동한다",
            ],
        },
    )
    assert response.status_code == 200
    assert len(response.json()["choices"]) >= 2
