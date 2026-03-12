from __future__ import annotations

from pathlib import Path

from app.agents.intender import IntenderAgent
from app.agents.narrator import NarratorAgent
from app.config import Settings, load_settings
from app.game.models import ContentBundle
from app.game.service import GameSessionService
from app.retrieval.indexer import index_documents
from app.retrieval.search import RetrievalService
from app.retrieval.vector_store import ChromaVectorStore
from app.services.llm_client import build_llm_client


class AgentRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ChromaVectorStore(settings.vector_store, settings.embedding)
        self.retrieval = RetrievalService(self.store, settings)
        self.intender = IntenderAgent(
            settings=settings.intender,
            llm_client=build_llm_client(settings.intender),
            retrieval=self.retrieval,
        )
        self.narrator = NarratorAgent(
            settings=settings.narrator,
            llm_client=build_llm_client(settings.narrator),
            retrieval=self.retrieval,
        )
        self.game = GameSessionService(
            content=ContentBundle.load_from_disk(game_content_root()),
            intender=self.intender,
            default_narrator=self.narrator,
            narrator_settings=settings.narrator,
        )
        self.index_counts = {"intender": 0, "narrator": 0}
        if settings.vector_store.auto_index_on_startup:
            self.index_counts = index_documents(self.store, retrieval_content_root())

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "intender": {
                "provider": self.settings.intender.provider,
                "model": self.settings.intender.model,
                "llmConfigured": bool(self.settings.intender.api_key) or self.settings.intender.provider == "mock",
            },
            "narrator": {
                "provider": self.settings.narrator.provider,
                "model": self.settings.narrator.model,
                "llmConfigured": bool(self.settings.narrator.api_key) or self.settings.narrator.provider == "mock",
            },
            "vectorStore": {
                "provider": self.settings.vector_store.provider,
                "path": str(self.settings.vector_store.persist_directory),
                "autoIndex": self.settings.vector_store.auto_index_on_startup,
                "collectionCounts": {
                    "intender": self.retrieval.collection_count("intender"),
                    "narrator": self.retrieval.collection_count("narrator"),
                },
                "indexedDocuments": self.index_counts,
            },
        }


_RUNTIME: AgentRuntime | None = None


def get_runtime() -> AgentRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = AgentRuntime(load_settings())
    return _RUNTIME


def content_root() -> Path:
    return Path(__file__).resolve().parents[1] / "content"


def retrieval_content_root() -> Path:
    return content_root()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def game_content_root() -> Path:
    return repo_root() / "content"


def frontend_root() -> Path:
    return repo_root() / "frontend"
