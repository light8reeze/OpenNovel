from app.schemas.narrative import NarrativeRequest, NarrativeResponse


OPENING_TEXT = (
    "{location_name}. 축축한 밤공기와 무너진 석재 사이로 오래 잠든 유적의 냄새가 스며 나온다. "
    "입구 아래로는 횃불빛조차 삼켜 버릴 것 같은 어둠이 천천히 입을 벌리고 있다."
)


TURN_TEXT = {
    "MOVE_OK": "당신은 조심스럽게 발걸음을 옮긴다. 공기 결이 미세하게 바뀌며 장면이 넘어간다.",
    "NOTHING_FOUND": "무너진 돌과 먼지를 훑어 보지만, 지금은 더 진행을 바꿀 만한 단서는 드러나지 않는다.",
    "NO_USEFUL_DIALOGUE": "짧은 대화는 오가지만, 상황을 바꿀 만큼 새로운 정보는 나오지 않는다.",
    "NO_NPC_TO_TALK": "주변에는 말을 걸어도 응답할 상대가 보이지 않는다.",
    "REST_OK": "잠시 숨을 고르자 차가운 공기 속에서도 맥박이 조금 가라앉는다.",
    "TORCH_LIT": "횃불 끝이 살아나며 주변의 금 간 벽면과 바닥의 먼지를 조금 더 또렷하게 비춘다.",
    "RETREAT_IGNORED": "당장은 발길을 돌릴 뿐, 유적 자체가 특별한 결말을 허락하지는 않는다.",
}


def render_opening(request: NarrativeRequest) -> NarrativeResponse:
    return NarrativeResponse(
        narrative=OPENING_TEXT.format(location_name=request.scene_context.location_name),
        choices=request.allowed_choices[:4],
        source="template",
        used_fallback=True,
    )


def render_turn(request: NarrativeRequest) -> NarrativeResponse:
    message_code = request.engine_result.message_code if request.engine_result else ""
    narrative = TURN_TEXT.get(
        message_code,
        "유적은 조용히 다음 반응을 기다리고 있다.",
    )
    return NarrativeResponse(
        narrative=narrative,
        choices=request.allowed_choices[:4],
        source="template",
        used_fallback=True,
    )
