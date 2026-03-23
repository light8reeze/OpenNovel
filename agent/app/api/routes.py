from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.game.models import ActionRequest, StartOptions, StartRequest
from app.game.service import InvalidActionRequestError, SessionNotFoundError
from app.runtime import get_runtime
from app.runtime import frontend_root
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse
from app.schemas.story_setup import StorySetupListResponse
from app.services.file_logger import (
    load_turn_log_bundle,
    log_backend_request,
    log_intent_result,
    log_narrative_result,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((frontend_root() / "index.html").read_text(encoding="utf-8"))


@router.get("/frontend/{asset_name}")
def frontend_asset(asset_name: str) -> FileResponse:
    return FileResponse(frontend_root() / asset_name)


@router.get("/health")
def health() -> dict[str, Any]:
    return get_runtime().health()


@router.get("/story-setups", response_model=StorySetupListResponse)
def story_setups() -> StorySetupListResponse:
    runtime = get_runtime()
    presets, source = runtime.game.available_story_setups()
    return StorySetupListResponse(presets=presets, source=source)


@router.get("/debug/turn-log")
def turn_log(sessionId: str, turn: int) -> dict[str, Any]:
    runtime = get_runtime()
    if not runtime.settings.debug_ui_enabled:
        raise HTTPException(status_code=404, detail="debug ui disabled")
    return load_turn_log_bundle(sessionId, turn)


@router.post("/intent/validate", response_model=IntentValidationResponse)
def validate_intent(payload: IntentValidationRequest) -> IntentValidationResponse:
    request_payload = payload.model_dump(mode="json")
    log_backend_request("/intent/validate", request_payload)
    response = get_runtime().intender.handle(payload)
    log_intent_result("/intent/validate", request_payload, response.model_dump(mode="json"))
    return response


@router.post("/narrative/opening", response_model=NarrativeResponse)
def opening_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    request_payload = payload.model_dump(mode="json")
    log_backend_request("/narrative/opening", request_payload)
    response = get_runtime().narrator.render_opening(payload)
    log_narrative_result("/narrative/opening", request_payload, response.model_dump(mode="json"))
    return response


@router.post("/narrative/turn", response_model=NarrativeResponse)
def turn_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    request_payload = payload.model_dump(mode="json")
    log_backend_request("/narrative/turn", request_payload)
    response = get_runtime().narrator.render_turn(payload)
    log_narrative_result("/narrative/turn", request_payload, response.model_dump(mode="json"))
    return response


@router.post("/game/start")
def start_game(payload: Optional[StartRequest] = None) -> Any:
    request = payload or StartRequest()
    request_payload = request.model_dump(mode="json", by_alias=True)
    log_backend_request("/game/start", request_payload)
    response = get_runtime().game.start_game(
        StartOptions(
            gemini_api_key=request.gemini_api_key,
            gemini_model=request.gemini_model,
            story_setup_id=request.story_setup_id,
        )
    )
    return response.model_dump(mode="json", by_alias=True)


@router.post("/game/action")
def apply_action(payload: ActionRequest) -> Any:
    request_payload = payload.model_dump(mode="json", by_alias=True)
    log_backend_request("/game/action", request_payload)
    try:
        response = get_runtime().game.apply_action(payload)
    except InvalidActionRequestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="session not found") from error
    return response.model_dump(mode="json", by_alias=True)


@router.get("/game/state")
def get_state(sessionId: str) -> Any:
    request_payload = {"sessionId": sessionId}
    log_backend_request("/game/state", request_payload)
    try:
        response = get_runtime().game.get_state(sessionId)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="session not found") from error
    return response.model_dump(mode="json", by_alias=True)
