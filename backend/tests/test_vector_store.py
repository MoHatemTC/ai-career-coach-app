"""Tests for the Qdrant vector store and its pipeline integration.

Uses qdrant-client's in-memory mode (`QdrantClient(":memory:")`) so nothing
here needs Docker or a network. The embedding model is stubbed out, so the
tests also never download model weights — what's under test is the wiring,
the point-ID derivation, and the payload contract, not the model itself.
"""

import uuid
from datetime import datetime, timezone

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.db_models import Base, IngestionRun, JobPostingORM
from backend.models.job import JobPosting
from backend.services import vector_store
from backend.services.vector_store import (
    COLLECTION_NAME,
    VECTOR_SIZE,
    build_embedding_text,
    build_payload,
    ensure_collection,
    job_point_id,
    upsert_job_embedding,
)


@pytest.fixture
def client():
    """A local in-memory Qdrant instance — no Docker, no network."""
    return QdrantClient(":memory:")


@pytest.fixture
def fake_model(monkeypatch):
    """Stub the shared model so tests never download real weights."""

    class _StubModel:
        def encode(self, text):
            # Deterministic, correctly-sized vector; content is irrelevant here.
            return [0.01] * VECTOR_SIZE

    monkeypatch.setattr(vector_store, "_model", _StubModel())
    return _StubModel()


def _job(job_id="abc123", title="Backend Engineer"):
    return JobPosting(
        job_id=job_id,
        title=title,
        company="Acme",
        location="Cairo, Egypt",
        description="Build ingestion services.",
        skills=["Python", "FastAPI"],
        source="Test",
        url="https://example.com/job/1",
        date=datetime.now(timezone.utc),
    )


def test_ensure_collection_creates_with_contract_dimensions(client):
    ensure_collection(client)

    assert client.collection_exists(COLLECTION_NAME)
    info = client.get_collection(COLLECTION_NAME)
    params = info.config.params.vectors
    assert params.size == VECTOR_SIZE == 384
    assert params.distance.lower() == "cosine"


def test_ensure_collection_is_idempotent(client):
    ensure_collection(client)
    ensure_collection(client)  # must not raise on an existing collection
    assert client.collection_exists(COLLECTION_NAME)


def test_point_id_is_deterministic_uuid5_of_job_id():
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, "abc123"))
    assert job_point_id("abc123") == expected
    assert job_point_id("abc123") == job_point_id("abc123")
    assert job_point_id("abc123") != job_point_id("different")
    # Must be a valid UUID — Qdrant rejects arbitrary hex strings as point IDs.
    uuid.UUID(job_point_id("abc123"))


def test_embedding_text_composition_is_the_documented_contract():
    text = build_embedding_text(_job())
    assert text == (
        "Title: Backend Engineer\n"
        "Skills: Python, FastAPI\n"
        "Description: Build ingestion services."
    )


def test_upsert_is_retrievable_by_derived_id_with_job_id_in_payload(client, fake_model):
    job = _job()
    ensure_collection(client)
    upsert_job_embedding(job, client=client)

    point_id = job_point_id(job.job_id)
    found = client.retrieve(collection_name=COLLECTION_NAME, ids=[point_id])

    assert len(found) == 1
    payload = found[0].payload
    # The real job_id round-trips in the payload, so a hit maps back to SQLite.
    assert payload["job_id"] == job.job_id
    assert payload["title"] == job.title
    assert payload["company"] == job.company
    assert payload["url"] == job.url
    assert payload["source"] == job.source


def test_reupserting_same_job_overwrites_rather_than_duplicating(client, fake_model):
    ensure_collection(client)
    upsert_job_embedding(_job(title="Backend Engineer"), client=client)
    upsert_job_embedding(_job(title="Senior Backend Engineer"), client=client)

    count = client.count(collection_name=COLLECTION_NAME).count
    assert count == 1  # same job_id -> same point ID -> overwrite

    found = client.retrieve(collection_name=COLLECTION_NAME, ids=[job_point_id("abc123")])
    assert found[0].payload["title"] == "Senior Backend Engineer"


def test_payload_carries_fields_needed_to_join_back_to_sqlite():
    payload = build_payload(_job())
    for key in ("job_id", "title", "company", "location", "url", "source"):
        assert key in payload


# --- pipeline integration: a Qdrant failure must not affect SQLite ------------


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def test_vector_failure_leaves_sqlite_counts_intact_and_run_not_failed(session, monkeypatch):
    """A broken vector store downgrades the run to 'partial' but never loses
    the SQLite writes, and never reports 'failed' — SQLite is authoritative."""
    from backend.services import ingestion_pipeline

    monkeypatch.setattr(
        ingestion_pipeline, "CLIENT_FACTORIES",
        {"mock_mena": ingestion_pipeline.CLIENT_FACTORIES["mock_mena"]},
    )

    def boom(jobs):
        raise ConnectionError("Qdrant unreachable")

    monkeypatch.setattr(ingestion_pipeline, "sync_batch_to_vector_store", boom)

    run = ingestion_pipeline.run_ingestion(
        sources=["mock_mena"], limit=5, session=session
    )

    # SQLite side is untouched by the vector failure.
    assert run.jobs_inserted > 0
    assert session.query(JobPostingORM).count() == run.jobs_inserted
    # Recorded, but not 'failed' — the authoritative write succeeded.
    assert run.status == "partial"
    assert "vector sync" in (run.error_message or "")
    assert run.jobs_embedded == 0


def test_successful_vector_sync_counts_embedded_and_keeps_success(session, monkeypatch):
    from backend.services import ingestion_pipeline

    monkeypatch.setattr(
        ingestion_pipeline, "sync_batch_to_vector_store", lambda jobs: len(list(jobs))
    )

    run = ingestion_pipeline.run_ingestion(
        sources=["mock_mena"], limit=5, session=session
    )

    assert run.status == "success"
    assert run.jobs_embedded == run.jobs_fetched
    assert run.error_message is None


def test_wrong_dimension_vector_raises_clear_error(monkeypatch):
    """A model whose output width drifts from the collection's configured size
    must fail loudly rather than corrupting the collection."""

    class _WrongSizeModel:
        def encode(self, text):
            return [0.01] * (VECTOR_SIZE - 1)

    monkeypatch.setattr(vector_store, "_model", _WrongSizeModel())

    with pytest.raises(ValueError, match="embedding contract"):
        vector_store.embed_job_posting(_job())
