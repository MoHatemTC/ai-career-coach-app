"""Matching lane's view of the shared job-posting vector store.

This module exists only so `backend.features.matching.retriever` keeps its
original import path working. It is deliberately a thin re-export — the real
implementation lives in `backend/services/vector_store.py`, next to the
ingestion pipeline that writes the collection.

Why one definition and not two: the writer (ingestion) and the reader
(matching) must agree on the model, vector size, distance metric and
collection name. If those drift, similarity search does not fail loudly — it
silently returns nonsense. Keeping a single module means they cannot drift.
See `docs/vector-store.md` for the frozen contract.

Both databases stay strictly local for this phase: Qdrant runs either embedded
(`QDRANT_MODE=local`) or against the docker-compose service on localhost:6333
(`QDRANT_MODE=server`). No hosted Qdrant, no API keys.
"""

from backend.services.vector_store import (  # noqa: F401
    COLLECTION_NAME,
    DISTANCE,
    EMBEDDING_MODEL_NAME,
    VECTOR_SIZE,
    build_embedding_text,
    build_payload,
    ensure_collection,
    get_embedding_model,
    get_qdrant_client,
)

__all__ = [
    "COLLECTION_NAME",
    "DISTANCE",
    "EMBEDDING_MODEL_NAME",
    "VECTOR_SIZE",
    "build_embedding_text",
    "build_payload",
    "ensure_collection",
    "get_embedding_model",
    "get_qdrant_client",
]
