"""Seed Qdrant with real job postings, end to end, then prove it's queryable.

Everything here is LOCAL: SQLite at the DATABASE_URL file path, Qdrant at
localhost:6333 via the docker-compose service. No cloud services, no API keys.

Prerequisites
-------------
1.  docker compose up -d qdrant
2.  pip install -r requirements.txt
    (the first run downloads the ~90MB all-MiniLM-L6-v2 model)

Run from the repo root:

    python scripts/seed_qdrant.py

What it does
------------
1. Checks Qdrant is actually reachable (fails fast with a clear message).
2. Runs the real ingestion pipeline, which persists postings to SQLite and
   then syncs their embeddings into the `job_postings` collection.
3. Reports how many vectors the collection now holds.
4. Runs a real similarity search with an arbitrary query string and prints the
   hits — proving the collection contains queryable vectors, not just rows.
"""

import sys
from pathlib import Path

# Running `python scripts/seed_qdrant.py` puts scripts/ on sys.path, not the
# repo root, so `import backend...` would fail. Add the repo root explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient  # noqa: E402

from backend.services.database import DATABASE_URL, init_db  # noqa: E402
from backend.services.ingestion_pipeline import run_ingestion  # noqa: E402
from backend.services.vector_store import (  # noqa: E402
    COLLECTION_NAME,
    EMBEDDING_MODEL_NAME,
    get_embedding_model,
    get_qdrant_client,
)

# Sources to seed from. mock_mena is offline and always works; the other two
# hit the live internet and may fail (Wuzzuf in particular is behind an
# intermittent Cloudflare challenge). A failing source is isolated by the
# pipeline and reported, it does not abort the run.
SOURCES = ["mock_mena", "arbeitnow", "wuzzuf"]
LIMIT = 10

# Arbitrary text, deliberately not copied from any posting, to show that
# retrieval is semantic rather than an exact-match lookup.
TEST_QUERY = "python backend engineer who builds data pipelines"


def check_qdrant() -> QdrantClient:
    try:
        client = get_qdrant_client()
        client.get_collections()
        print(f"[ok] Qdrant reachable, collections: "
              f"{[c.name for c in client.get_collections().collections]}")
        return client
    except Exception as exc:
        sys.exit(
            f"[fail] Cannot reach Qdrant: {exc}\n"
            "       Start it first:  docker compose up -d qdrant\n"
            "       Expected at localhost:6333 (override with QDRANT_HOST/QDRANT_PORT)."
        )


def main() -> None:
    print(f"SQLite : {DATABASE_URL}")
    print("Qdrant : localhost:6333 (docker-compose service)\n")

    client = check_qdrant()

    print("\n[1/4] Creating SQLite tables if needed...")
    init_db()

    print(f"[2/4] Running ingestion for {SOURCES} (limit {LIMIT} each)...")
    print("      First run downloads the embedding model; this can take a minute.")
    run = run_ingestion(sources=SOURCES, limit=LIMIT)
    print(
        f"      status={run.status}  fetched={run.jobs_fetched}  "
        f"inserted={run.jobs_inserted}  updated={run.jobs_updated}  "
        f"skipped={run.jobs_skipped}  embedded={run.jobs_embedded}"
    )
    if run.error_message:
        print(f"      note: {run.error_message}")

    print("\n[3/4] Checking the collection...")
    if not client.collection_exists(COLLECTION_NAME):
        sys.exit(f"[fail] Collection {COLLECTION_NAME!r} was never created.")
    count = client.count(collection_name=COLLECTION_NAME).count
    print(f"      {COLLECTION_NAME}: {count} vector(s)")
    if count == 0:
        sys.exit(
            "[fail] Collection is empty — nothing was embedded. Check the run's "
            "error_message above."
        )

    print(f"\n[4/4] Similarity search for: {TEST_QUERY!r}")
    # Embed the query exactly the way jobs are embedded (see docs/vector-store.md).
    query_vector = get_embedding_model().encode(TEST_QUERY).tolist()
    hits = client.query_points(
        collection_name=COLLECTION_NAME, query=query_vector, limit=5
    ).points

    if not hits:
        sys.exit("[fail] Search returned no hits despite a non-empty collection.")

    for i, hit in enumerate(hits, 1):
        p = hit.payload or {}
        print(f"  {i}. score={hit.score:.4f}  {p.get('title')} @ {p.get('company')}")
        print(f"     source={p.get('source')}  job_id={p.get('job_id')}")

    print(
        f"\n[done] Qdrant is seeded and queryable "
        f"({count} vectors, model {EMBEDDING_MODEL_NAME})."
    )


if __name__ == "__main__":
    main()
