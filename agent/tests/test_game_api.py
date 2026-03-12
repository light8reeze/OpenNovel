from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_start_game_returns_rust_compatible_shape() -> None:
    response = client.post("/game/start", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["sessionId"].startswith("session-")
    assert payload["state"]["meta"]["turn"] == 0
    assert payload["choices"] == ["주변을 조사한다", "관리인과 대화한다", "회랑으로 이동한다"]


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


def test_good_ending_path_matches_rust_demo() -> None:
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
        message_codes.append(payload["engineResult"]["message_code"])

    assert message_codes == [
        "NOTHING_FOUND",
        "MOVE_OK",
        "NOTHING_FOUND",
        "MOVE_OK",
        "NOTHING_FOUND",
        "MOVE_OK",
        "NOTHING_FOUND",
        "NOTHING_FOUND",
        "MOVE_OK",
        "MOVE_OK",
        "MOVE_OK",
        "NOTHING_FOUND",
    ]
    final_state = payload["state"]
    assert final_state["quests"]["sunken_ruins"]["stage"] == 0
    assert final_state["player"]["gold"] == 15
    assert payload["engineResult"]["ending_reached"] is None


def test_frontend_shell_is_served_from_agent() -> None:
    index = client.get("/")
    script = client.get("/frontend/app.js")
    assert index.status_code == 200
    assert "OpenNovel MVP" in index.text
    assert script.status_code == 200
    assert "startGame" in script.text
