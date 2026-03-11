from fastapi import APIRouter
from typing import Any

from app.config import load_settings
from app.graph.workflow import narrative_workflow, validate_intent_workflow
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse
from app.services.file_logger import (
    log_backend_request,
    log_intent_result,
    log_narrative_result,
)

router = APIRouter()
SETTINGS = load_settings()


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "provider": SETTINGS.llm_provider,
        "model": SETTINGS.llm_model,
        "llmConfigured": bool(SETTINGS.llm_api_key) or SETTINGS.llm_provider == "mock",
    }


@router.post("/intent/validate", response_model=IntentValidationResponse)
def validate_intent(payload: IntentValidationRequest) -> IntentValidationResponse:
    request_payload = payload.model_dump(mode="json")
    log_backend_request("/intent/validate", request_payload)
    response = validate_intent_workflow(payload)
    log_intent_result(
        "/intent/validate",
        request_payload,
        response.model_dump(mode="json"),
    )
    return response


@router.post("/narrative/opening", response_model=NarrativeResponse)
def opening_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    request_payload = payload.model_dump(mode="json")
    log_backend_request("/narrative/opening", request_payload)
    response = narrative_workflow("opening", payload)
    log_narrative_result(
        "/narrative/opening",
        request_payload,
        response.model_dump(mode="json"),
    )
    return response


@router.post("/narrative/turn", response_model=NarrativeResponse)
def turn_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    request_payload = payload.model_dump(mode="json")
    log_backend_request("/narrative/turn", request_payload)
    response = narrative_workflow("turn", payload)
    log_narrative_result(
        "/narrative/turn",
        request_payload,
        response.model_dump(mode="json"),
    )
    return response
