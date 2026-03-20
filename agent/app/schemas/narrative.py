from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import EngineResult, SceneContext, StateSummary, TokenUsage


class NarrativeRequest(BaseModel):
    state_summary: StateSummary
    scene_context: SceneContext
    engine_result: Optional[EngineResult] = None
    allowed_choices: list[str] = Field(default_factory=list)


class NarrativeLlmResponse(BaseModel):
    narrative: str
    choices: list[str] = Field(default_factory=list)
    source: str
    used_fallback: bool = False
    safety_flags: list[str] = Field(default_factory=list)


class NarrativeResponse(BaseModel):
    narrative: str
    choices: list[str] = Field(default_factory=list)
    source: str
    provider: str = ""
    model: str = ""
    used_fallback: bool = False
    retrieval_used: bool = False
    retrieved_document_ids: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
