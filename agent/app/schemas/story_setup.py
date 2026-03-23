from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StorySetup(BaseModel):
    id: str
    title: str
    world_summary: str
    tone: str
    player_goal: str
    opening_hook: str
    style_guardrails: list[str] = Field(default_factory=list)


class StorySetupListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    presets: list[StorySetup] = Field(default_factory=list)
    source: str


class StorySetupGenerationResponse(BaseModel):
    presets: list[StorySetup] = Field(default_factory=list)

