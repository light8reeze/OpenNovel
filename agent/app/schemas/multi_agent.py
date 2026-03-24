from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.game.models import GameState
from app.schemas.common import Action, EngineResult, TokenUsage
from app.schemas.story import StoryMessage
from app.schemas.story_setup import StorySetup


class WorldLocation(BaseModel):
    id: str
    label: str
    kind: str = "location"
    connections: list[str] = Field(default_factory=list)
    danger_level: int = 1
    investigation_hooks: list[str] = Field(default_factory=list)


class WorldNpc(BaseModel):
    id: str
    label: str
    home_location_id: str
    role: str = ""
    interaction_hint: str = ""


class WorldBlueprint(BaseModel):
    id: str
    title: str
    world_summary: str
    tone: str
    core_conflict: str
    player_goal: str
    opening_hook: str
    starting_location_id: str = "opening_location"
    locations: list[WorldLocation] = Field(default_factory=list)
    npcs: list[WorldNpc] = Field(default_factory=list)
    notable_locations: list[str] = Field(default_factory=list)
    important_npcs: list[str] = Field(default_factory=list)
    hidden_truths: list[str] = Field(default_factory=list)


class WorldBuildRequest(BaseModel):
    story_setup: StorySetup


class WorldBuildResponse(BaseModel):
    blueprint: WorldBlueprint
    source: str
    provider: str = ""
    model: str = ""
    used_fallback: bool = False
    token_usage: Optional[TokenUsage] = None


class StoryTransitionProposalRequest(BaseModel):
    state: GameState
    world_blueprint: WorldBlueprint
    discovery_log: list[str] = Field(default_factory=list)
    history: list[StoryMessage] = Field(default_factory=list)
    intent: Action


class StoryTransitionProposalDraft(BaseModel):
    scene_summary: str
    state_patch: dict[str, Any] = Field(default_factory=dict)
    discovered_facts: list[str] = Field(default_factory=list)
    choice_candidates: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)


class StoryTransitionProposalResponse(BaseModel):
    scene_summary: str
    state_patch: dict[str, Any] = Field(default_factory=dict)
    discovered_facts: list[str] = Field(default_factory=list)
    choice_candidates: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    source: str
    provider: str = ""
    model: str = ""
    used_fallback: bool = False
    token_usage: Optional[TokenUsage] = None


class ValidationResult(BaseModel):
    state: GameState
    engine_result: EngineResult
    allowed_choices: list[str] = Field(default_factory=list)
    discovery_log: list[str] = Field(default_factory=list)
    scene_summary: str = ""
    progress_kind: str = "continue"
    validation_flags: list[str] = Field(default_factory=list)
    source: str = "validator"
