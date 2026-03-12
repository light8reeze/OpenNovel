from app.schemas.narrative import NarrativeRequest, NarrativeResponse


OPENING_TEXT = (
    "{location_name}. 축축한 밤공기와 무너진 석재 사이로 오래 잠든 유적의 냄새가 스며 나온다. "
    "입구 아래로는 횃불빛조차 삼켜 버릴 것 같은 어둠이 천천히 입을 벌리고 있다."
)


TURN_TEXT = {
    "MOVE_OK": "당신은 조심스럽게 발걸음을 옮긴다. 공기 결이 미세하게 바뀌며 장면이 넘어간다.",
    "RUNE_FOUND": "무너진 입구의 문양 사이에서 희미한 봉인 흔적이 드러난다.",
    "PASSAGE_OPENED": "갈라진 회랑의 틈새가 서서히 열리며 더 깊은 길을 허락한다.",
    "TRAP_REVEALED": "바닥을 가로지르는 얕은 홈과 눌린 돌이 함정의 질서를 드러낸다.",
    "SEAL_BROKEN": "오래 버티던 봉인이 마른 숨을 토하듯 갈라지며 제단의 어둠을 연다.",
    "RELIC_SECURED": "제단 중심에서 차가운 유물이 손안으로 미끄러지며 유적 전체가 낮게 떨린다.",
    "RELIC_RECOVERED": "끝내 유물을 품에 안고 입구의 밤공기 속으로 돌아온다.",
    "CARETAKER_BRIEFING": "관리인은 낮은 목소리로 유적의 봉인과 후퇴 시점을 짧게 일러 준다.",
    "CARETAKER_WARNING": "관리인은 더 깊이 들어갈수록 욕심보다 발걸음을 먼저 의심하라고 경고한다.",
    "CURSE_TRIGGERED": "후퇴하려는 순간 어둠이 발목을 감싸며 유적의 저주가 뒤늦게 깨어난다.",
    "RETREAT_END": "당신은 등을 돌리고 밤의 바람 속으로 빠져나온다. 유적은 다시 침묵한다.",
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
