"""Route tests for the ingestion API's read endpoints.

Covers the response contract the Streamlit dashboard depends on — in
particular that `jobs_embedded` is exposed, since it is the signal that the
Qdrant vector sync is keeping up with SQLite.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db_models import Base, IngestionRun
from backend.routes.ingestion import router
from backend.services.database import get_db


@pytest.fixture
def ctx():
    # StaticPool keeps every connection on the SAME in-memory database;
    # without it the dependency's session opens a fresh, tableless one.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSession


def _seed_run(SessionFactory, **overrides):
    fields = dict(
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        source="mock_mena",
        jobs_fetched=5,
        jobs_inserted=3,
        jobs_updated=2,
        jobs_skipped=0,
        jobs_embedded=4,
        status="success",
    )
    fields.update(overrides)
    db = SessionFactory()
    run = IngestionRun(**fields)
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    db.close()
    return run_id


def test_get_run_exposes_jobs_embedded(ctx):
    """The counter is persisted AND returned — without this the dashboard
    cannot show vector-sync health."""
    client, SessionFactory = ctx
    run_id = _seed_run(SessionFactory, jobs_embedded=4)

    body = client.get(f"/ingestion/runs/{run_id}").json()

    assert "jobs_embedded" in body
    assert body["jobs_embedded"] == 4


def test_list_runs_exposes_jobs_embedded(ctx):
    client, SessionFactory = ctx
    _seed_run(SessionFactory, jobs_embedded=7)

    body = client.get("/ingestion/runs").json()

    assert len(body) == 1
    assert body[0]["jobs_embedded"] == 7


def test_lagging_embed_count_is_visible(ctx):
    """jobs_embedded < inserted + updated is the documented signal that the
    vector store is behind; it must survive the API boundary."""
    client, SessionFactory = ctx
    run_id = _seed_run(
        SessionFactory, jobs_inserted=3, jobs_updated=2, jobs_embedded=0,
        status="partial", error_message="mock_mena (vector sync): boom",
    )

    body = client.get(f"/ingestion/runs/{run_id}").json()

    assert body["jobs_embedded"] == 0
    assert body["jobs_inserted"] + body["jobs_updated"] == 5
    assert body["status"] == "partial"
    assert "vector sync" in body["error_message"]


def test_get_unknown_run_is_404(ctx):
    client, _ = ctx
    assert client.get("/ingestion/runs/9999").status_code == 404


def test_runs_are_newest_first(ctx):
    client, SessionFactory = ctx
    first = _seed_run(SessionFactory, source="first")
    second = _seed_run(SessionFactory, source="second")

    body = client.get("/ingestion/runs").json()

    assert [r["id"] for r in body] == [second, first]
