from typing import Any

from fastapi import APIRouter

from app.runtime import get_runtime
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse
from app.services.file_logger import log_backend_request, log_intent_result, log_narrative_result

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return get_runtime().health()


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
