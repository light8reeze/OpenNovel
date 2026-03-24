from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    MOVE = "MOVE"
    TALK = "TALK"
    ATTACK = "ATTACK"
    INVESTIGATE = "INVESTIGATE"
    REST = "REST"
    USE_ITEM = "USE_ITEM"
    FLEE = "FLEE"
    TRADE = "TRADE"


class Action(BaseModel):
    action_type: ActionType
    target: Optional[str] = None
    raw_input: str


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False


class StateSummary(BaseModel):
    turn: int
    location_id: str
    hp: int
    gold: int
    story_arc_stage: int
    player_flags: list[str] = Field(default_factory=list)


class SceneContext(BaseModel):
    location_name: str
    npcs_in_scene: list[str] = Field(default_factory=list)
    visible_targets: list[str] = Field(default_factory=list)


class EngineResult(BaseModel):
    success: bool
    message_code: str
    location_changed: bool
    quest_stage_changed: bool
    ending_reached: Optional[str] = None
    details: list[str] = Field(default_factory=list)
