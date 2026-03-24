from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import EngineResult, SceneContext, StateSummary, TokenUsage


class NarrativeRequest(BaseModel):
    state_summary: StateSummary
    scene_context: SceneContext
    engine_result: Optional[EngineResult] = None
    allowed_choices: list[str] = Field(default_factory=list)
    scene_summary: Optional[str] = None
    discovery_log: list[str] = Field(default_factory=list)
    world_title: Optional[str] = None
    world_summary: Optional[str] = None
    world_tone: Optional[str] = None
    player_goal: Optional[str] = None
    opening_hook: Optional[str] = None


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
