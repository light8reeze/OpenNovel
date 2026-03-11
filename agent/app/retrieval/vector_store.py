from __future__ import annotations

import math
from hashlib import sha256
from typing import Iterable

import chromadb
from chromadb.api.models.Collection import Collection

from app.config import EmbeddingSettings, VectorStoreSettings


class LocalHashEmbeddingFunction:
    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def __call__(self, input: Iterable[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def embed_documents(self, input: Iterable[str]) -> list[list[float]]:
        return self.__call__(input)

    def embed_query(self, input: Iterable[str]) -> list[list[float]]:
        return self.__call__(input)

    def name(self) -> str:
        return "local-hash-embedding"

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine"]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        normalized = text.strip().lower()
        if not normalized:
            return vector
        for token in normalized.split():
            digest = sha256(token.encode("utf-8")).digest()
            for index in range(self.dimensions):
                vector[index] += digest[index % len(digest)] / 255.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class ChromaVectorStore:
    def __init__(self, settings: VectorStoreSettings, embedding: EmbeddingSettings):
        self.settings = settings
        self.embedding = LocalHashEmbeddingFunction(embedding.dimensions)
        settings.persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(settings.persist_directory))

    def get_collection(self, role: str) -> Collection:
        return self.client.get_or_create_collection(
            name=f"{self.settings.collection_prefix}_{role}",
            embedding_function=self.embedding,
        )

    def collection_count(self, role: str) -> int:
        return self.get_collection(role).count()
