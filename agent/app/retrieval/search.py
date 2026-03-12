from __future__ import annotations

from app.config import Settings
from app.retrieval.query_builder import build_intender_query, build_narrator_query
from app.retrieval.schemas import RetrievalContext, RetrievalHit
from app.retrieval.vector_store import ChromaVectorStore
from app.schemas.intent import IntentValidationRequest
from app.schemas.narrative import NarrativeRequest


class RetrievalService:
    def __init__(self, store: ChromaVectorStore, settings: Settings):
        self.store = store
        self.settings = settings

    def search_for_intender(self, request: IntentValidationRequest) -> RetrievalContext:
        query = build_intender_query(request)
        raw_hits = self._query("intender", query)
        filtered = [
            hit
            for hit in raw_hits
            if self._matches_location(hit.metadata, request.state_summary.location_id)
            and self._matches_stage(hit.metadata, request.state_summary.sunken_ruins_stage)
        ]
        return RetrievalContext(used=bool(filtered), query=query, hits=filtered[: self.settings.vector_store.top_k])

    def search_for_narrator(self, kind: str, request: NarrativeRequest) -> RetrievalContext:
        query = build_narrator_query(kind, request)
        raw_hits = self._query("narrator", query)
        filtered = [
            hit
            for hit in raw_hits
            if self._matches_visibility(hit.metadata, "player")
            and self._matches_location(hit.metadata, request.state_summary.location_id)
            and not self._is_quest_stage_doc(hit.metadata)
        ]
        return RetrievalContext(used=bool(filtered), query=query, hits=filtered[: self.settings.vector_store.top_k])

    def collection_count(self, role: str) -> int:
        return self.store.collection_count(role)

    def _query(self, role: str, query: str) -> list[RetrievalHit]:
        collection = self.store.get_collection(role)
        if collection.count() == 0:
            return []
        result = collection.query(query_texts=[query], n_results=max(self.settings.vector_store.top_k * 2, 4))
        documents = result.get("documents", [[]])[0]
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        hits = []
        for doc_id, text, metadata in zip(ids, documents, metadatas):
            hits.append(RetrievalHit(id=doc_id, text=text, metadata=metadata or {}))
        return hits

    def _matches_location(self, metadata: dict[str, object], location_id: str) -> bool:
        candidate = metadata.get("location_id")
        return candidate in (None, "", location_id)

    def _matches_stage(self, metadata: dict[str, object], stage: int) -> bool:
        stage_min = metadata.get("stage_min")
        stage_max = metadata.get("stage_max")
        if isinstance(stage_min, int) and stage < stage_min:
            return False
        if isinstance(stage_max, int) and stage > stage_max:
            return False
        return True

    def _matches_visibility(self, metadata: dict[str, object], visibility: str) -> bool:
        candidate = metadata.get("visibility")
        return candidate in (None, "", visibility)

    def _is_quest_stage_doc(self, metadata: dict[str, object]) -> bool:
        tags = metadata.get("tags")
        if isinstance(tags, list):
            return "quest" in tags
        return False
