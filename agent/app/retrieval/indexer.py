from __future__ import annotations

import json
from pathlib import Path

from app.retrieval.schemas import RetrievalDocument
from app.retrieval.vector_store import ChromaVectorStore


def index_documents(store: ChromaVectorStore, content_root: Path) -> dict[str, int]:
    counts = {"intender": 0, "narrator": 0}
    for role in counts:
        documents = _load_documents(content_root / f"{role}_docs")
        if not documents:
            continue
        collection = store.get_collection(role)
        collection.upsert(
            ids=[document.id for document in documents],
            documents=[document.text for document in documents],
            metadatas=[document.model_dump(exclude={"id", "text"}) for document in documents],
        )
        counts[role] = len(documents)
    return counts


def _load_documents(directory: Path) -> list[RetrievalDocument]:
    if not directory.exists():
        return []
    documents: list[RetrievalDocument] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = [payload]
        for item in payload:
            documents.append(RetrievalDocument.model_validate(item))
    return documents
