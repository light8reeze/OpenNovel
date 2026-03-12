from app.schemas.intent import IntentValidationRequest
from app.schemas.narrative import NarrativeRequest


def build_intender_query(request: IntentValidationRequest) -> str:
    return " | ".join(
        [
            request.player_input,
            request.state_summary.location_id,
            ",".join(request.scene_context.visible_targets),
            ",".join(action.value for action in request.allowed_actions),
        ]
    )


def build_narrator_query(kind: str, request: NarrativeRequest) -> str:
    engine_code = request.engine_result.message_code if request.engine_result else "GAME_STARTED"
    return " | ".join(
        [
            kind,
            request.scene_context.location_name,
            request.state_summary.location_id,
            f"stage={request.state_summary.sunken_ruins_stage}",
            engine_code,
            ",".join(request.scene_context.npcs_in_scene),
        ]
    )
