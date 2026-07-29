"""Seed Qdrant with real job postings and run a test similarity search.

Fetches real jobs via the existing ingestion clients, embeds each posting,
upserts into the local Qdrant collection, then runs one real query against
it to prove retrieval actually works end-to-end — not just that the script
ran without errors.

Run from the repo root:
    python scripts/seed_qdrant.py
"""
import sys
from pathlib import Path

# Same fix as verify_ingestion.py: put repo root on sys.path so `backend.*`
# imports work when running this file directly, not just via -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.ingestion import (
    ArbeitnowIngestionClient,
    WuzzufScraperClient,
    MockMenaIngestionClient,
)
from backend.services.vector_store import (
    get_qdrant_client,
    ensure_collection,
    get_embedding_model,
    upsert_job_embedding,
)


def fetch_real_postings(limit_per_source=5):
    """Pull a handful of real postings per source. A failing source is
    logged and skipped, not fatal — seeding continues with whatever
    succeeded, same failure-isolation pattern as the ingestion pipeline."""
    postings = []
    for name, client in [
        ("arbeitnow", ArbeitnowIngestionClient()),
        ("wuzzuf", WuzzufScraperClient()),
        ("mock_mena", MockMenaIngestionClient()),
    ]:
        try:
            jobs = client.get_jobs(limit=limit_per_source)
            print(f"[{name}] fetched {len(jobs)} postings")
            postings.extend(jobs)
        except Exception as exc:
            print(f"[{name}] failed: {type(exc).__name__}: {exc}")
    return postings


def main():
    print("Connecting to Qdrant (local mode)...")
    client = get_qdrant_client()          # ONE client, reused everywhere below
    ensure_collection(client)
    print("Collection ready.\n")

    print("Loading embedding model (first run downloads it once, cached after)...")
    get_embedding_model()
    print("Model loaded.\n")

    print("Fetching real job postings...")
    postings = fetch_real_postings()
    if not postings:
        print("Nothing fetched from any source — aborting.")
        return

    print(f"\nEmbedding and upserting {len(postings)} postings...")
    for job in postings:
        upsert_job_embedding(job, client=client)   # <-- pass the same client in
    print("Seed complete.\n")

    query_text = "Python backend developer with FastAPI and SQL experience"
    print(f"Running test similarity search for: {query_text!r}\n")
    model = get_embedding_model()
    query_vector = model.encode(query_text).tolist()

    results = client.query_points(
        collection_name="job_postings",
        query=query_vector,
        limit=5,
    ).points

    print("=" * 72)
    print("TOP MATCHES")
    print("=" * 72)
    for i, point in enumerate(results, 1):
        p = point.payload
        print(f"{i}. score={point.score:.4f}  {p.get('title')} @ {p.get('company')}")
        print(f"   location: {p.get('location')}   source: {p.get('source')}")
        print(f"   job_id:   {p.get('job_id')}\n")


if __name__ == "__main__":
    main()
