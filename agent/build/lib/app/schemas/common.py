from __future__ import annotations

from enum import Enum

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
    target: str | None = None
    raw_input: str


class StateSummary(BaseModel):
    turn: int
    location_id: str
    hp: int
    gold: int
    murder_case_stage: int
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
    ending_reached: str | None = None
    details: list[str] = Field(default_factory=list)
