"""Tests for the persistence/upsert layer against an in-memory SQLite DB."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.db_models import Base, IngestionRun, JobPostingORM
from backend.models.job import JobPosting
from backend.services.ingestion_pipeline import upsert_job_postings


@pytest.fixture
def session():
    """A fresh in-memory SQLite session per test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _job(job_id="abc123", title="Backend Engineer", description="Original text"):
    return JobPosting(
        job_id=job_id,
        title=title,
        company="Acme",
        location="Cairo, Egypt",
        description=description,
        skills=["Python"],
        source="Test",
        url="https://example.com/job/1",
        date=datetime.now(timezone.utc),
    )


class _StubClient:
    """Stands in for a source client, returning a fixed batch."""

    def __init__(self, jobs):
        self._jobs = jobs

    def get_jobs(self, limit=10):
        return self._jobs[:limit]


def _new_run(session):
    run = IngestionRun(started_at=datetime.now(timezone.utc), source="test", status="running")
    session.add(run)
    session.commit()
    return run


def test_upsert_updates_existing_job_instead_of_duplicating(session):
    run = _new_run(session)

    # First ingestion: inserts one row.
    upsert_job_postings(session, [_job()], run)
    session.commit()

    assert session.query(JobPostingORM).count() == 1
    assert run.jobs_inserted == 1
    assert run.jobs_updated == 0

    # Second ingestion: same job_id, changed fields -> update in place.
    run2 = _new_run(session)
    upsert_job_postings(
        session,
        [_job(title="Senior Backend Engineer", description="Corrected text")],
        run2,
    )
    session.commit()

    # Still exactly one row (deduped by job_id), and it carries the new values.
    assert session.query(JobPostingORM).count() == 1
    row = session.get(JobPostingORM, "abc123")
    assert row.title == "Senior Backend Engineer"
    assert row.description == "Corrected text"
    assert run2.jobs_updated == 1
    assert run2.jobs_inserted == 0


def test_invalid_posting_is_skipped_not_crashing(session):
    run = _new_run(session)

    # A raw dict with a blank title fails JobPosting validation; a valid
    # JobPosting alongside it must still persist.
    invalid = {
        "job_id": "bad1",
        "title": "   ",  # blank -> fails not_blank validator
        "company": "Acme",
        "location": "Cairo",
        "description": "x",
        "skills": [],
        "source": "Test",
        "url": "https://example.com/bad",
        "date": datetime.now(timezone.utc),
    }

    upsert_job_postings(session, [invalid, _job(job_id="good1")], run)
    session.commit()

    assert run.jobs_skipped == 1
    assert run.jobs_inserted == 1
    assert session.query(JobPostingORM).count() == 1
    assert session.get(JobPostingORM, "good1") is not None
    assert session.get(JobPostingORM, "bad1") is None


def test_run_ingestion_prunes_stale_embeddings(session, monkeypatch):
    """Reconciliation must happen on every automated run, not only when someone
    remembers to run the seed script by hand."""
    from backend.services import ingestion_pipeline

    pruned_calls = []
    monkeypatch.setattr(
        ingestion_pipeline, "_build_client",
        lambda name, run_id=None: _StubClient([_job(job_id="a1")]),
    )
    monkeypatch.setattr(
        ingestion_pipeline, "sync_batch_to_vector_store", lambda jobs: len(list(jobs))
    )
    monkeypatch.setattr(
        ingestion_pipeline, "prune_stale_embeddings",
        lambda sess: pruned_calls.append(sess) or ["orphan"],
    )

    run = ingestion_pipeline.run_ingestion(
        sources=["mock_mena"], limit=1, session=session
    )

    assert len(pruned_calls) == 1
    assert run.status == "success"


def test_reconciliation_failure_does_not_fail_the_run(session, monkeypatch):
    """An unreachable Qdrant must not fail a run whose SQLite writes worked."""
    from backend.services import ingestion_pipeline

    monkeypatch.setattr(
        ingestion_pipeline, "_build_client",
        lambda name, run_id=None: _StubClient([_job(job_id="a1")]),
    )
    monkeypatch.setattr(
        ingestion_pipeline, "sync_batch_to_vector_store", lambda jobs: len(list(jobs))
    )

    def _boom(sess):
        raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr(ingestion_pipeline, "prune_stale_embeddings", _boom)

    run = ingestion_pipeline.run_ingestion(
        sources=["mock_mena"], limit=1, session=session
    )

    assert run.status == "partial"
    assert "reconciliation" in (run.error_message or "")
