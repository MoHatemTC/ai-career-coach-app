"""Seed both stores with real job postings and run a test similarity search.

Fetches real jobs via the existing ingestion clients, writes them to SQLite,
embeds each posting into the local Qdrant collection, then runs one real query
against it to prove retrieval actually works end-to-end — not just that the
script ran without errors.

WHY IT WRITES SQLITE TOO
------------------------
It originally seeded Qdrant only, which quietly broke the explanation stage:
`attach_explanations` joins each ranked posting back from SQLite on `job_id` to
recover the skills the Qdrant payload does not carry, so a job present in
Qdrant but absent from SQLite gets no explanation at all. Seeding one store and
not the other produced exactly that drift, and the symptom was every card
falling back to a placeholder with only a log line to explain it.

Both writes happen here for the same reason the pipeline does them together:
SQLite is the source of truth, Qdrant is a derived index.

Run from the repo root, with the backend NOT running (embedded Qdrant allows a
single process at a time):
    python scripts/seed_qdrant.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

# Same fix as verify_ingestion.py: put repo root on sys.path so `backend.*`
# imports work when running this file directly, not just via -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models.db_models import IngestionRun
from backend.services.database import SessionLocal, init_db
from backend.services.ingestion import (
    ArbeitnowIngestionClient,
    WuzzufScraperClient,
    MockMenaIngestionClient,
)
from backend.services.ingestion_pipeline import upsert_job_postings
from backend.services.vector_store import (
    get_qdrant_client,
    ensure_collection,
    get_embedding_model,
    upsert_job_embedding,
)


def persist_to_sqlite(postings):
    """Upsert the fetched postings into SQLite and report the counts.

    Reuses the pipeline's `upsert_job_postings` so dedup behaves identically to
    a real ingestion run rather than being reimplemented here.
    """
    init_db()
    session = SessionLocal()
    try:
        run = IngestionRun(
            started_at=datetime.now(timezone.utc),
            source="seed_qdrant",
            status="running",
            jobs_fetched=len(postings),
            jobs_inserted=0,
            jobs_updated=0,
            jobs_skipped=0,
            jobs_embedded=0,
        )
        session.add(run)
        session.commit()

        upsert_job_postings(session, postings, run)
        run.finished_at = datetime.now(timezone.utc)
        run.status = "success"
        session.commit()
        return run.jobs_inserted, run.jobs_updated, run.jobs_skipped
    finally:
        session.close()


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

    # SQLite first, so a posting can never be in Qdrant without being in the
    # database — the direction of drift that breaks the explanation stage.
    print("Writing postings to SQLite...")
    inserted, updated, skipped = persist_to_sqlite(postings)
    print(f"SQLite: {inserted} inserted, {updated} updated, {skipped} skipped.\n")

    print(f"Embedding and upserting {len(postings)} postings into Qdrant...")
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
