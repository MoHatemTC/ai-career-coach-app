"""Sanity-check the retrieval lane's output before trusting it downstream.

Calls `backend.features.matching.retriever.retrieve_top_jobs` directly — the
real function the pipeline uses — and prints what comes back, then checks the
things that break the stages after it. The seed script's own test query talks to
Qdrant directly, so it proves the collection is queryable but says nothing about
this function.

What it verifies, and why each matters:

1. The payload carries exactly the keys the contract promises. The re-ranker's
   prompt and the UI both read these by name; a renamed field degrades silently
   rather than raising.
2. Scores are ordered descending. Retrieval is supposed to hand the re-ranker a
   ranked shortlist.
3. Every returned job_id exists in SQLite. This is the one that bit us: the
   explanation stage joins postings back from SQLite on job_id, so a job present
   in Qdrant but absent from the database gets no explanation and the UI quietly
   falls back to a placeholder.
4. Similarity is discriminating. If a backend-flavoured query scores a frontend
   role as highly as a backend one, the embedding contract is not doing its job
   even though nothing errored.

Run from the repo root with the backend NOT running (embedded Qdrant allows one
process at a time):
    python scripts/verify_retrieval.py
    python scripts/verify_retrieval.py "data analyst with SQL and Power BI"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.features.matching.retriever import retrieve_top_jobs
from backend.models.db_models import JobPostingORM
from backend.services.database import SessionLocal, init_db

# The keys docs/vector-store.md promises in every hit, plus the score the
# retriever adds. The re-ranker and UI read these by name.
EXPECTED_KEYS = {
    "job_id", "title", "company", "location", "url", "source", "match_score",
}

DEFAULT_QUERY = "Python backend developer with FastAPI and SQL experience"
CONTRAST_QUERY = "Frontend developer with React and CSS"


def check_payload_keys(jobs):
    problems = []
    for job in jobs:
        missing = EXPECTED_KEYS - set(job)
        extra = set(job) - EXPECTED_KEYS
        if missing:
            problems.append(f"  {job.get('job_id')}: missing {sorted(missing)}")
        if extra:
            problems.append(f"  {job.get('job_id')}: unexpected {sorted(extra)}")
    return problems


def check_ordering(jobs):
    scores = [j.get("match_score") for j in jobs]
    if scores != sorted(scores, reverse=True):
        return [f"  scores are not descending: {scores}"]
    return []


def check_sqlite_presence(jobs):
    """The exact lookup the explanation stage performs."""
    init_db()
    session = SessionLocal()
    try:
        missing = [
            job.get("job_id")
            for job in jobs
            if session.get(JobPostingORM, job.get("job_id")) is None
        ]
    finally:
        session.close()
    if missing:
        return [
            f"  {len(missing)} job(s) are in Qdrant but NOT in SQLite: {missing}",
            "  -> explanations will be skipped for these and the UI will show",
            "     placeholders. Re-run: python scripts/seed_qdrant.py",
        ]
    return []


def show(query, jobs):
    print(f"\nQuery: {query!r}")
    print("-" * 72)
    if not jobs:
        print("  (nothing returned — is the collection seeded?)")
        return
    for i, job in enumerate(jobs, 1):
        print(f"{i}. score={job.get('match_score'):.4f}  "
              f"{job.get('title')} @ {job.get('company')}")
        print(f"   source={job.get('source')}  job_id={job.get('job_id')}")


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    print("Calling retrieve_top_jobs (the real function the pipeline uses)...")
    jobs = retrieve_top_jobs(cv_text=query, top_k=5)
    show(query, jobs)

    if not jobs:
        print("\nFAIL: retrieval returned nothing. Seed first.")
        return 1

    problems = (
        check_payload_keys(jobs) + check_ordering(jobs) + check_sqlite_presence(jobs)
    )

    # A contrasting query should not score the same way. This catches an
    # embedding contract that runs without erroring but does not discriminate.
    contrast = retrieve_top_jobs(cv_text=CONTRAST_QUERY, top_k=5)
    show(CONTRAST_QUERY, contrast)
    if contrast and jobs:
        top_same = contrast[0].get("job_id") == jobs[0].get("job_id")
        print(
            f"\nTop hit differs between the two queries: {'NO' if top_same else 'YES'}"
        )
        if top_same:
            problems.append(
                "  both queries returned the same top hit — similarity may not "
                "be discriminating, or the collection is too small to tell"
            )

    print("\n" + "=" * 72)
    if problems:
        print("PROBLEMS FOUND")
        print("=" * 72)
        for line in problems:
            print(line)
        return 1
    print("All checks passed: keys, ordering, SQLite presence, discrimination.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
