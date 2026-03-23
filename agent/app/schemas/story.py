from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.game.models import GameState
from app.schemas.common import Action, EngineResult, TokenUsage
from app.schemas.story_setup import StorySetup


class StoryMessage(BaseModel):
    role: str
    content: str


class StoryTurnRequest(BaseModel):
    mode: str
    state: GameState
    history: list[StoryMessage] = Field(default_factory=list)
    player_input: Optional[str] = None
    story_setup: StorySetup


class StoryActionDraft(BaseModel):
    action_type: Optional[str] = None
    target: Optional[str] = None
    raw_input: Optional[str] = None


class StoryEngineResultDraft(BaseModel):
    success: bool = True
    message_code: Optional[str] = None
    message: Optional[str] = None
    location_changed: Optional[bool] = None
    quest_stage_changed: Optional[bool] = None
    ending_reached: Optional[str] = None
    details: list[str] = Field(default_factory=list)


class StoryTurnDraft(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    narrative: str
    choices: list[str] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    engine_result: Optional[StoryEngineResultDraft] = Field(default=None, alias="engineResult")
    action: Optional[StoryActionDraft] = None


class StoryTurnResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    narrative: str
    choices: list[str] = Field(default_factory=list)
    state: GameState
    engine_result: EngineResult = Field(alias="engineResult")
    action: Optional[Action] = None
    source: str
    provider: str = ""
    model: str = ""
    used_fallback: bool = False
    retrieval_used: bool = False
    retrieved_document_ids: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
