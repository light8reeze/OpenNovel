from app.runtime import get_runtime
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse


def validate_intent_workflow(request: IntentValidationRequest) -> IntentValidationResponse:
    return get_runtime().intender.handle(request)


def narrative_workflow(kind: str, request: NarrativeRequest) -> NarrativeResponse:
    narrator = get_runtime().narrator
    if kind == "opening":
        return narrator.render_opening(request)
    return narrator.render_turn(request)
