from fastapi import APIRouter
from typing import Any

from app.config import load_settings
from app.graph.workflow import narrative_workflow, validate_intent_workflow
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse

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
    return validate_intent_workflow(payload)


@router.post("/narrative/opening", response_model=NarrativeResponse)
def opening_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    return narrative_workflow("opening", payload)


@router.post("/narrative/turn", response_model=NarrativeResponse)
def turn_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    return narrative_workflow("turn", payload)
