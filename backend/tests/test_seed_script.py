"""Tests for scripts/seed_qdrant.py's SQLite write.

The script originally seeded Qdrant only. That silently broke the explanation
stage: `attach_explanations` joins each ranked posting back from SQLite on
`job_id`, so a job in Qdrant but not in the database gets no explanation and the
UI falls back to a placeholder, with only a log line to say why. Every card was
affected and the pipeline still returned 200.
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db_models import Base, JobPostingORM
from backend.models.job import JobPosting

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "seed_qdrant.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("seed_qdrant", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seed(monkeypatch):
    """Load the script with its DB pointed at an in-memory database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    module = _load_script()
    monkeypatch.setattr(module, "SessionLocal", Session)
    monkeypatch.setattr(module, "init_db", lambda: None)
    return module, Session


def _posting(job_id="a1") -> JobPosting:
    return JobPosting(
        job_id=job_id,
        title="Backend Engineer",
        company="Acme",
        location="Cairo",
        description="Build APIs.",
        skills=["python"],
        source="wuzzuf",
        url=f"https://example.com/{job_id}",
        date=datetime.now(timezone.utc),
    )


def test_postings_land_in_sqlite(seed):
    """Without this the explanation join fails for every ranked job."""
    module, Session = seed

    inserted, updated, skipped = module.persist_to_sqlite([_posting("a1")])

    db = Session()
    rows = db.query(JobPostingORM).all()
    db.close()
    assert [r.job_id for r in rows] == ["a1"]
    assert inserted == 1


def test_reseeding_updates_rather_than_duplicating(seed):
    module, Session = seed

    module.persist_to_sqlite([_posting("a1")])
    inserted, updated, _ = module.persist_to_sqlite([_posting("a1")])

    db = Session()
    count = db.query(JobPostingORM).count()
    db.close()
    assert count == 1
    assert updated == 1 and inserted == 0


def test_the_ranked_job_ids_are_findable_afterwards(seed):
    """The exact lookup attach_explanations performs, on the ids the retriever
    would return from the Qdrant payload."""
    module, Session = seed
    module.persist_to_sqlite([_posting("aaa"), _posting("bbb")])

    db = Session()
    found = [db.get(JobPostingORM, jid) for jid in ("aaa", "bbb")]
    db.close()
    assert all(row is not None for row in found)
