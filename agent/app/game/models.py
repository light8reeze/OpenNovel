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


class WorldState(BaseModel):
    time: str
    global_flags: list[str] = Field(default_factory=list)
    alert_by_region: dict[str, int] = Field(default_factory=dict)


class QuestProgress(BaseModel):
    stage: int


class QuestState(BaseModel):
    sunken_ruins: QuestProgress


class RelationsState(BaseModel):
    npc_affinity: dict[str, int] = Field(default_factory=dict)


class GameState(BaseModel):
    meta: MetaState
    player: PlayerState
    world: WorldState
    quests: QuestState
    relations: RelationsState

    def summary(self) -> "StateSummary":
        from app.schemas.common import StateSummary

        return StateSummary(
            turn=self.meta.turn,
            location_id=self.player.location_id,
            hp=self.player.hp,
            gold=self.player.gold,
            sunken_ruins_stage=self.quests.sunken_ruins.stage,
            player_flags=list(self.player.flags),
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


class ContentBundle(BaseModel):
    locations: list[Location]
    npcs: list[Npc]
    sunken_ruins: QuestDefinition

    @classmethod
    def load_from_disk(cls, root: Path) -> "ContentBundle":
        import json

        locations = [Location.model_validate(item) for item in json.loads((root / "locations.json").read_text(encoding="utf-8"))]
        npcs = [Npc.model_validate(item) for item in json.loads((root / "npcs.json").read_text(encoding="utf-8"))]
        sunken_ruins = QuestDefinition.model_validate(
            json.loads((root / "quests" / "sunken_ruins.json").read_text(encoding="utf-8"))
        )
        location_ids = {location.id for location in locations}
        for location in locations:
            for connection in location.connections:
                if connection not in location_ids:
                    raise ValueError(f"location '{location.id}' references unknown connection '{connection}'")
        for npc in npcs:
            if npc.location_id not in location_ids:
                raise ValueError(f"npc '{npc.id}' references unknown location '{npc.location_id}'")
        return cls(locations=locations, npcs=npcs, sunken_ruins=sunken_ruins)

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




def initial_state() -> GameState:
    return GameState(
        meta=MetaState(turn=0, seed=12345),
        player=PlayerState(
            hp=100,
            gold=15,
            location_id="ruins_entrance",
            inventory=dict(Counter({"torch": 1})),
            flags=[],
        ),
        world=WorldState(
            time="night",
            global_flags=["sunken_ruins_open"],
            alert_by_region={"ruins": 6},
        ),
        quests=QuestState(sunken_ruins=QuestProgress(stage=0)),
        relations=RelationsState(npc_affinity={"caretaker": 5}),
    )
