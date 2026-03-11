from app.schemas.narrative import NarrativeRequest, NarrativeResponse


OPENING_TEXT = (
    "{location_name}. 축축한 밤공기 속에서 마을은 숨을 죽인 채 가라앉아 있다. "
    "멀리서 문이 닫히는 둔탁한 소리가 한 번 울린다."
)


TURN_TEXT = {
    "MOVE_OK": "당신은 조심스럽게 발걸음을 옮긴다. 공기 결이 미세하게 바뀌며 장면이 넘어간다.",
    "BLOOD_MARK_FOUND": "젖은 바닥의 틈에서 마르다 만 핏자국이 모습을 드러낸다.",
    "BLOODY_CLOTH_FOUND": "낡은 상자 틈에서 피가 눌어붙은 천 조각이 천천히 끌려 나온다.",
    "ARIA_CLUE_CONFIRMED": "아리아는 손에 든 단서를 보자 숨을 삼키고 낮은 목소리로 기억을 꺼낸다.",
    "SHADOW_TRACKED": "골목의 진흙 바닥에 깊게 찍힌 자국이 다음 장소를 가리킨다.",
    "INNKEEPER_TESTIMONY": "여관 주인은 오래 망설인 끝에 밤중의 목격담을 털어놓는다.",
    "GOOD_END_UNLOCKED": "흩어진 조각들이 하나로 맞물리며 사건의 윤곽이 또렷해진다.",
    "BAD_END_FLEE": "당신이 등을 돌리자 진실은 어둠 속으로 더 깊이 가라앉는다.",
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
        "상황은 움직였지만 아직 모든 실마리가 이어진 것은 아니다.",
    )
    return NarrativeResponse(
        narrative=narrative,
        choices=request.allowed_choices[:4],
        source="template",
        used_fallback=True,
    )
