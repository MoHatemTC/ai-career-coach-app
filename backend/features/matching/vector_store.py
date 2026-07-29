"""Qdrant connection + collection constants for the matching lane.

`backend/features/matching/retriever.py` imports `get_qdrant_client` and
`COLLECTION_NAME` from this module, but the module itself was never committed,
so `backend.main` failed to import at all. This restores it.

THE EMBEDDING CONTRACT — these values are not free parameters
-------------------------------------------------------------
The ingestion lane writes the `job_postings` collection; this lane reads it.
Both sides must agree or the vectors are not comparable and queries silently
return nonsense. The frozen contract (see `docs/vector-store.md`) is:

- Model:       sentence-transformers "all-MiniLM-L6-v2"
- Vector size: 384 (that model's output dimensionality)
- Distance:    Cosine
- Collection:  "job_postings"

Keep the constants below identical to the writer's. The full vector-store
module (embedding, upsert, search) lands with the ingestion-side vector work;
when it does, this file collapses into a re-export of it so there is exactly
one definition of these values.

Both databases are strictly local for this phase: Qdrant runs either embedded
(`QDRANT_MODE=local`) or against the docker-compose service on localhost:6333
(`QDRANT_MODE=server`). No hosted/cloud Qdrant, no API keys.
"""

import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()

COLLECTION_NAME = "job_postings"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_SIZE = 384


def get_qdrant_client() -> QdrantClient:
    """Return a Qdrant client for the mode configured in the environment.

    `local` is the embedded, file-backed mode — no Docker needed, but it takes
    an exclusive lock on the storage directory, so only one process can hold it
    at a time. Use `server` when the backend and a script both need the
    collection at once (`docker compose up -d qdrant`).
    """
    mode = os.getenv("QDRANT_MODE", "local")
    if mode == "local":
        return QdrantClient(path=os.getenv("QDRANT_LOCAL_PATH", "./qdrant_local_data"))
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", 6333)),
    )
