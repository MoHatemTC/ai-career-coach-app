"""Tests for reconciling Qdrant against SQLite.

Qdrant never deleted anything: `upsert_job_embedding` overwrites by
deterministic id but never removes, so every posting ever embedded stayed
forever. Combined with sources that return different results between runs, the
collection accumulated postings SQLite no longer had. Those orphans can still
win retrieval and then get no explanation, so the user sees a placeholder card
for a job the database has never heard of.

Uses qdrant-client's in-memory mode and an in-memory SQLite database.
"""

from datetime import datetime, timezone

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db_models import Base, job_posting_to_orm
from backend.models.job import JobPosting
from backend.services.vector_store import (
    delete_job_embeddings,
    ensure_collection,
    prune_orphaned_embeddings,
    stored_job_ids,
    upsert_job_embedding,
)


@pytest.fixture
def client():
    qdrant = QdrantClient(":memory:")
    ensure_collection(qdrant)
    return qdrant


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield db
    db.close()


def _posting(job_id) -> JobPosting:
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


def test_stored_job_ids_lists_what_is_in_the_collection(client):
    upsert_job_embedding(_posting("a1"), client=client)
    upsert_job_embedding(_posting("b2"), client=client)

    assert sorted(stored_job_ids(client)) == ["a1", "b2"]


def test_stored_job_ids_pages_past_the_scroll_limit(client):
    """Scroll must page, or the result silently truncates as the collection
    grows and orphans past the first page are never found."""
    for i in range(300):
        upsert_job_embedding(_posting(f"job{i:04d}"), client=client)

    assert len(stored_job_ids(client)) == 300


def test_delete_removes_the_point(client):
    upsert_job_embedding(_posting("a1"), client=client)

    assert delete_job_embeddings(["a1"], client=client) == 1
    assert stored_job_ids(client) == []


def test_delete_of_nothing_is_a_noop(client):
    assert delete_job_embeddings([], client=client) == 0


def test_prune_removes_only_the_orphans(client, session):
    """The point of the whole thing: a posting in Qdrant with no SQLite row is
    stale by definition, since SQLite is the source of truth."""
    session.add(job_posting_to_orm(_posting("kept")))
    session.commit()
    upsert_job_embedding(_posting("kept"), client=client)
    upsert_job_embedding(_posting("orphan"), client=client)

    removed = prune_orphaned_embeddings(session, client)

    assert removed == ["orphan"]
    assert stored_job_ids(client) == ["kept"]


def test_prune_is_a_noop_when_the_stores_agree(client, session):
    session.add(job_posting_to_orm(_posting("a1")))
    session.commit()
    upsert_job_embedding(_posting("a1"), client=client)

    assert prune_orphaned_embeddings(session, client) == []
    assert stored_job_ids(client) == ["a1"]


def test_prune_leaves_an_empty_collection_alone(client, session):
    assert prune_orphaned_embeddings(session, client) == []
