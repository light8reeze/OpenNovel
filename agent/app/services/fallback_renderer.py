from app.schemas.narrative import NarrativeRequest, NarrativeResponse


OPENING_TEXT = (
    "{world_title}. {opening_hook} "
    "{world_summary}"
)


TURN_TEXT = {
    "MOVE_OK": "당신은 조심스럽게 발걸음을 옮긴다. 공기 결이 미세하게 바뀌며 장면이 넘어간다.",
    "INVESTIGATE_PROGRESS": "주변의 흐름을 더듬다 보니 지금 장면을 다음 단계로 밀어 줄 작은 실마리가 드러난다.",
    "DIALOGUE_PROGRESS": "짧은 대화가 오간 뒤, 상황을 보는 각도와 다음 움직임의 방향이 조금 더 선명해진다.",
    "NO_NPC_TO_TALK": "주변에는 말을 걸어도 응답할 상대가 보이지 않는다.",
    "REST_OK": "잠시 숨을 고르자 차가운 공기 속에서도 맥박이 조금 가라앉는다.",
    "USE_ITEM_OK": "손에 쥔 도구를 써 보자 숨겨져 있던 질감과 단서가 조금 더 또렷해진다.",
    "RETREAT_OK": "한 걸음 물러서며 방금까지의 압박과 다음 선택을 다시 가늠한다.",
}


def render_opening(request: NarrativeRequest) -> NarrativeResponse:
    world_title = request.world_title or request.scene_context.location_name
    opening_hook = request.opening_hook or f"{request.scene_context.location_name}에서 이야기가 시작된다."
    world_summary = (request.world_summary or "").strip()
    if world_summary:
        world_summary = world_summary.split(".")[0].strip()
    return NarrativeResponse(
        narrative=OPENING_TEXT.format(
            world_title=world_title,
            opening_hook=opening_hook,
            world_summary=world_summary,
        ).strip(),
        choices=request.allowed_choices[:4],
        source="template",
        used_fallback=True,
    )


def render_turn(request: NarrativeRequest) -> NarrativeResponse:
    message_code = request.engine_result.message_code if request.engine_result else ""
    narrative = request.scene_summary or TURN_TEXT.get(
        message_code,
        f"{request.scene_context.location_name}의 공기가 미세하게 흔들리며 다음 반응을 기다리고 있다.",
    )
    if request.progress_kind == "stalled":
        narrative = request.scene_summary or (
            f"{request.scene_context.location_name}에서는 이미 확인한 단서와 분위기가 되풀이되고 있어, 다른 접근이 더 필요해 보인다."
        )
    if request.discovery_log:
        latest = request.discovery_log[-1].rstrip(". ")
        if latest and latest not in narrative:
            narrative = f"{narrative} {latest}."
    return NarrativeResponse(
        narrative=narrative,
        choices=request.allowed_choices[:4],
        source="template",
        used_fallback=True,
    )
