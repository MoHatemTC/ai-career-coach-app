"""Qdrant vector store for job postings — the retrieval side of ingestion.

This is an *additional* write target, not a replacement: SQLite
(`job_postings` / `ingestion_runs`) remains the source of truth for dedup and
run history. Qdrant holds one embedding per posting so the matching lane can
run similarity search (e.g. CV -> nearest jobs).

THE EMBEDDING CONTRACT (frozen — see docs/vector-store.md)
----------------------------------------------------------
Anything that queries this collection must embed its query text the *same*
way, or the vectors are not comparable. The contract is:

- Model:       sentence-transformers "all-MiniLM-L6-v2" (the same model
               `backend/features/matching/scorer.py` already uses — this is
               deliberately not a second, separate choice).
- Vector size: 384 (all-MiniLM-L6-v2's output dimensionality).
- Distance:    Cosine.
- Collection:  "job_postings".
- Text blob:   title, then skills (comma-joined), then description, joined
               by newlines and labelled — see `build_embedding_text`. The
               labels are part of the contract; do not reorder or relabel.
- Point ID:    uuid5(NAMESPACE_URL, job_id). Qdrant point IDs must be an
               unsigned int or a UUID, and our `job_id` is a sha256-derived
               hex string, so it cannot be used directly. The derivation is
               deterministic, so re-embedding the same posting overwrites its
               point rather than duplicating it. The real `job_id` is stored
               in the payload so a hit maps straight back to the SQLite row.
"""

import os
import uuid
from typing import List, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.models.job import JobPosting

load_dotenv()

COLLECTION_NAME = "job_postings"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_SIZE = 384
DISTANCE = Distance.COSINE

# Namespace for deriving Qdrant point IDs from job_id. NAMESPACE_URL is used
# because job_id is itself derived from the posting URL.
POINT_ID_NAMESPACE = uuid.NAMESPACE_URL

_model = None


def get_embedding_model():
    """Load the shared sentence-transformers model once, on first use.

    Loaded lazily (not at import time) so that importing this module — or the
    ingestion pipeline that depends on it — does not pull ~90MB of model
    weights. Tests that do not exercise real embeddings never trigger it.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def get_qdrant_client() -> QdrantClient:
    """Connect to Qdrant using QDRANT_HOST / QDRANT_PORT (default localhost:6333)."""
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port)


def ensure_collection(client: Optional[QdrantClient] = None) -> None:
    """Create the `job_postings` collection if it does not already exist."""
    client = client or get_qdrant_client()
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=DISTANCE),
        )


def build_embedding_text(job: JobPosting) -> str:
    """Compose the exact text blob that gets embedded for a posting.

    Part of the frozen contract (see module docstring): title, skills, and
    description, labelled and newline-joined. Kept as its own function so the
    composition is inspectable and testable rather than buried in the encode
    call — anything embedding a query against this collection should mirror
    this shape.
    """
    skills = ", ".join(job.skills) if job.skills else ""
    return (
        f"Title: {job.title}\n"
        f"Skills: {skills}\n"
        f"Description: {job.description}"
    )


def embed_job_posting(job: JobPosting) -> List[float]:
    """Encode a posting into a `VECTOR_SIZE`-dim vector using the shared model."""
    text = build_embedding_text(job)
    vector = get_embedding_model().encode(text)
    # .encode returns a numpy array; Qdrant wants a plain list of floats.
    vector = vector.tolist() if hasattr(vector, "tolist") else list(vector)

    # The collection is created with a fixed vector size, so a model whose
    # output width differs would otherwise fail deep inside Qdrant with an
    # opaque error (or, worse, silently mismatch a differently-configured
    # collection). Fail loudly and early instead.
    if len(vector) != VECTOR_SIZE:
        raise ValueError(
            f"{EMBEDDING_MODEL_NAME} produced {len(vector)}-dim vectors, but the "
            f"{COLLECTION_NAME} collection is configured for {VECTOR_SIZE}. "
            "Update VECTOR_SIZE and docs/vector-store.md together, and recreate "
            "the collection — this is a breaking change to the embedding contract."
        )
    return vector


def job_point_id(job_id: str) -> str:
    """Derive the deterministic Qdrant point ID (UUID5) from a `job_id`."""
    return str(uuid.uuid5(POINT_ID_NAMESPACE, job_id))


def build_payload(job: JobPosting) -> dict:
    """Payload stored alongside the vector, for mapping hits back to SQLite."""
    return {
        "job_id": job.job_id,  # the real key into the job_postings table
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "url": job.url,
        "source": job.source,
    }


def upsert_job_embedding(job: JobPosting, client: Optional[QdrantClient] = None) -> None:
    """Upsert one posting's embedding into the collection.

    Idempotent: the point ID is derived deterministically from `job_id`, so
    re-ingesting a posting overwrites its existing point — mirroring the
    upsert-by-`job_id` behaviour of the SQLite layer.
    """
    client = client or get_qdrant_client()
    point = PointStruct(
        id=job_point_id(job.job_id),
        vector=embed_job_posting(job),
        payload=build_payload(job),
    )
    client.upsert(collection_name=COLLECTION_NAME, points=[point])
