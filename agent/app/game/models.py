from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Action, EngineResult
from app.schemas.story_setup import StorySetup


class MetaState(BaseModel):
    turn: int
    seed: int


class PlayerState(BaseModel):
    hp: int
    gold: int
    location_id: str
    inventory: dict[str, int] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    style_scores: dict[str, int] = Field(default_factory=dict)
    style_tags: list[str] = Field(default_factory=list)


class WorldState(BaseModel):
    time: str
    global_flags: list[str] = Field(default_factory=list)
    alert_by_region: dict[str, int] = Field(default_factory=dict)
    theme_id: Optional[str] = None
    theme_rules: list[str] = Field(default_factory=list)


class QuestProgress(BaseModel):
    stage: int


class QuestState(BaseModel):
    story_arc: QuestProgress


class ObjectiveState(BaseModel):
    status: str = "in_progress"
    victory_path: Optional[str] = None


class RelationsState(BaseModel):
    npc_affinity: dict[str, int] = Field(default_factory=dict)


class GameState(BaseModel):
    meta: MetaState
    player: PlayerState
    world: WorldState
    quests: QuestState
    objective: ObjectiveState = Field(default_factory=ObjectiveState)
    relations: RelationsState

    def summary(self) -> "StateSummary":
        from app.schemas.common import StateSummary

        return StateSummary(
            turn=self.meta.turn,
            location_id=self.player.location_id,
            hp=self.player.hp,
            gold=self.player.gold,
            story_arc_stage=self.quests.story_arc.stage,
            player_flags=list(self.player.flags),
            theme_id=self.world.theme_id,
            style_tags=list(self.player.style_tags),
            objective_status=self.objective.status,
            victory_path=self.objective.victory_path,
        )

    def has_flag(self, flag: str) -> bool:
        return flag in self.player.flags or flag in self.world.global_flags


class TurnResult(BaseModel):
    narrative: str
    choices: list[str] = Field(default_factory=list)
    state: GameState
    engine_result: EngineResult


class StartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    gemini_api_key: Optional[str] = Field(default=None, alias="geminiApiKey")
    gemini_model: Optional[str] = Field(default=None, alias="geminiModel")
    story_setup_id: Optional[str] = Field(default=None, alias="storySetupId")


class StartResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    narrative: str
    choices: list[str] = Field(default_factory=list)
    state: GameState
    story_setup_id: Optional[str] = Field(default=None, alias="storySetupId")


class ActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    input_text: Optional[str] = Field(default=None, alias="inputText")
    choice_text: Optional[str] = Field(default=None, alias="choiceText")


class ActionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    narrative: str
    choices: list[str] = Field(default_factory=list)
    engine_result: EngineResult = Field(alias="engineResult")
    state: GameState
    story_setup_id: Optional[str] = Field(default=None, alias="storySetupId")


class StateResponse(BaseModel):
    state: GameState
    story_setup_id: Optional[str] = Field(default=None, alias="storySetupId")


class ChoicesResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    choices: list[str] = Field(default_factory=list)
    story_setup_id: Optional[str] = Field(default=None, alias="storySetupId")


class Location(BaseModel):
    id: str
    name: str
    description: str
    connections: list[str] = Field(default_factory=list)


class Npc(BaseModel):
    id: str
    name: str
    location_id: str
    role: str


class QuestStageDefinition(BaseModel):
    stage: int
    summary: str


class QuestDefinition(BaseModel):
    id: str
    title: str
    stages: list[QuestStageDefinition] = Field(default_factory=list)
    endings: list[str] = Field(default_factory=list)


class ThemeNpcRole(BaseModel):
    id: str
    label: str
    role: str
    interaction_hint: str = ""
    location_index: int = 0


class ThemeVictoryPath(BaseModel):
    id: str
    label: str
    required_action: str
    required_location_index: int = -1
    min_stage: int = 0
    details: list[str] = Field(default_factory=list)


class ThemePack(BaseModel):
    id: str
    title_prefix: str
    summary_prefix: str
    tone: str
    opening_hook: str
    rules: list[str] = Field(default_factory=list)
    npc_roles: list[ThemeNpcRole] = Field(default_factory=list)
    victory_paths: list[ThemeVictoryPath] = Field(default_factory=list)
    alert_actions: list[str] = Field(default_factory=list)
    style_bias: dict[str, dict[str, int]] = Field(default_factory=dict)


class ContentBundle(BaseModel):
    locations: list[Location]
    npcs: list[Npc]
    story_arc: QuestDefinition
    theme_packs: list[ThemePack] = Field(default_factory=list)

    @classmethod
    def load_from_disk(cls, root: Path) -> "ContentBundle":
        import json

        locations = [Location.model_validate(item) for item in json.loads((root / "locations.json").read_text(encoding="utf-8"))]
        npcs = [Npc.model_validate(item) for item in json.loads((root / "npcs.json").read_text(encoding="utf-8"))]
        story_arc = QuestDefinition.model_validate(
            json.loads((root / "quests" / "sunken_ruins.json").read_text(encoding="utf-8"))
        )
        theme_packs_path = root / "theme_packs.json"
        theme_packs = []
        if theme_packs_path.exists():
            theme_packs = [ThemePack.model_validate(item) for item in json.loads(theme_packs_path.read_text(encoding="utf-8"))]
        location_ids = {location.id for location in locations}
        for location in locations:
            for connection in location.connections:
                if connection not in location_ids:
                    raise ValueError(f"location '{location.id}' references unknown connection '{connection}'")
        for npc in npcs:
            if npc.location_id not in location_ids:
                raise ValueError(f"npc '{npc.id}' references unknown location '{npc.location_id}'")
        return cls(locations=locations, npcs=npcs, story_arc=story_arc, theme_packs=theme_packs)

    def location_name(self, location_id: str) -> str:
        for location in self.locations:
            if location.id == location_id:
                return location.name
        return location_id


@dataclass(frozen=True)
class Event:
    kind: str
    value: Any = None


@dataclass(frozen=True)
class Resolution:
    action: Action
    events: list[Event]
    next_state: GameState
    engine_result: EngineResult


@dataclass(frozen=True)
class StartOptions:
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    story_setup_id: Optional[str] = None

def initial_state(seed: int = 12345) -> GameState:
    return GameState(
        meta=MetaState(turn=0, seed=seed),
        player=PlayerState(
            hp=100,
            gold=15,
            location_id="opening_location",
            inventory=dict(Counter({"torch": 1})),
            flags=[],
            style_scores={},
            style_tags=[],
        ),
        world=WorldState(
            time="night",
            global_flags=[],
            alert_by_region={},
            theme_id=None,
            theme_rules=[],
        ),
        quests=QuestState(story_arc=QuestProgress(stage=0)),
        objective=ObjectiveState(),
        relations=RelationsState(npc_affinity={}),
    )
