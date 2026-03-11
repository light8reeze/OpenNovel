from pydantic import BaseModel, Field

from app.schemas.common import Action, ActionType, SceneContext, StateSummary


class IntentValidationRequest(BaseModel):
    player_input: str
    allowed_actions: list[ActionType] = Field(default_factory=list)
    state_summary: StateSummary
    scene_context: SceneContext


class IntentValidationResponse(BaseModel):
    action: Action
    confidence: float
    validation_flags: list[str] = Field(default_factory=list)
    source: str
