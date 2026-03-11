from pydantic import BaseModel, Field

from app.schemas.common import EngineResult, SceneContext, StateSummary


class NarrativeRequest(BaseModel):
    state_summary: StateSummary
    scene_context: SceneContext
    engine_result: EngineResult | None = None
    allowed_choices: list[str] = Field(default_factory=list)


class NarrativeResponse(BaseModel):
    narrative: str
    choices: list[str] = Field(default_factory=list)
    source: str
    used_fallback: bool = False
    safety_flags: list[str] = Field(default_factory=list)
