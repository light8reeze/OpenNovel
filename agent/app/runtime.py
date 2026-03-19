from __future__ import annotations

from pathlib import Path

from app.agents.intender import IntenderAgent
from app.agents.narrator import NarratorAgent
from app.agents.story import StoryAgent
from app.config import Settings, load_settings
from app.game.models import ContentBundle
from app.game.service import GameSessionService
from app.retrieval.indexer import index_documents
from app.retrieval.search import RetrievalService
from app.retrieval.vector_store import ChromaVectorStore
from app.services.llm_client import LlmError, build_llm_client


class AgentRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ChromaVectorStore(settings.vector_store, settings.embedding)
        self.retrieval = RetrievalService(self.store, settings)
        self.content = ContentBundle.load_from_disk(game_content_root())
        self._intender: IntenderAgent | None = None
        self._narrator: NarratorAgent | None = None
        self._story_agent: StoryAgent | None = None
        self._game: GameSessionService | None = None
        self._intender_error: str | None = None
        self._narrator_error: str | None = None
        self._story_agent_error: str | None = None
        self._game_error: str | None = None
        self.index_counts = {"intender": 0, "narrator": 0}
        if settings.vector_store.auto_index_on_startup:
            self.index_counts = index_documents(self.store, retrieval_content_root())

    @property
    def story_agent(self) -> StoryAgent:
        if self._story_agent is None:
            try:
                self._story_agent = StoryAgent(
                    settings=self.settings.narrator,
                    llm_client=build_llm_client(self.settings.narrator),
                    retrieval=self.retrieval,
                )
                self._story_agent_error = None
            except LlmError as error:
                self._story_agent_error = str(error)
                raise
        return self._story_agent

    @property
    def intender(self) -> IntenderAgent:
        if self._intender is None:
            try:
                self._intender = IntenderAgent(
                    settings=self.settings.intender,
                    llm_client=build_llm_client(self.settings.intender),
                    retrieval=self.retrieval,
                )
                self._intender_error = None
            except LlmError as error:
                self._intender_error = str(error)
                raise
        return self._intender

    @property
    def narrator(self) -> NarratorAgent:
        if self._narrator is None:
            try:
                self._narrator = NarratorAgent(
                    settings=self.settings.narrator,
                    llm_client=build_llm_client(self.settings.narrator),
                    retrieval=self.retrieval,
                )
                self._narrator_error = None
            except LlmError as error:
                self._narrator_error = str(error)
                raise
        return self._narrator

    @property
    def game(self) -> GameSessionService:
        if self._game is None:
            try:
                self._game = GameSessionService(
                    content=self.content,
                    default_story_agent=self.story_agent,
                    story_agent_settings=self.settings.narrator,
                )
                self._game_error = None
            except LlmError as error:
                self._game_error = str(error)
                raise
        return self._game

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "intender": {
                "provider": self.settings.intender.provider,
                "model": self.settings.intender.model,
                "llmConfigured": bool(self.settings.intender.api_key) or self.settings.intender.provider == "mock",
                "runtimeError": self._intender_error,
            },
            "narrator": {
                "provider": self.settings.narrator.provider,
                "model": self.settings.narrator.model,
                "llmConfigured": bool(self.settings.narrator.api_key) or self.settings.narrator.provider == "mock",
                "runtimeError": self._narrator_error,
            },
            "storyAgent": {
                "provider": self.settings.narrator.provider,
                "model": self.settings.narrator.model,
                "llmConfigured": bool(self.settings.narrator.api_key) or self.settings.narrator.provider == "mock",
                "runtimeError": self._story_agent_error,
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
            "game": {
                "runtimeError": self._game_error,
            },
            "debugUiEnabled": self.settings.debug_ui_enabled,
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
