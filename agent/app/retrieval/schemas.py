from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RetrievalDocument(BaseModel):
    id: str
    role: str
    text: str
    location_id: Optional[str] = None
    npc_id: Optional[str] = None
    quest_id: Optional[str] = None
    stage_min: Optional[int] = None
    stage_max: Optional[int] = None
    visibility: str = "player"
    tags: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    id: str
    text: str
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievalContext(BaseModel):
    used: bool = False
    query: str = ""
    hits: list[RetrievalHit] = Field(default_factory=list)

    @property
    def document_ids(self) -> list[str]:
        return [hit.id for hit in self.hits]

    def as_prompt_block(self) -> str:
        if not self.hits:
            return ""
        return "\n".join(f"- {hit.text}" for hit in self.hits)
