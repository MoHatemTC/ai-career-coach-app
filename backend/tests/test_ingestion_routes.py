"""Route tests for the ingestion API's read endpoints.

Covers the response contract the Streamlit dashboard depends on — in
particular that `jobs_embedded` is exposed, since it is the signal that the
Qdrant vector sync is keeping up with SQLite.
"""

import json
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


# --- GET /ingestion/stats ----------------------------------------------------
#
# The landing page renders these numbers as evidence that the pipeline is real,
# so the contract that matters is that every figure is counted rather than
# estimated, and that an empty pool reports emptiness instead of a placeholder.


def _seed_job(SessionFactory, job_id, skills, source="Arbeitnow"):
    from backend.models.db_models import JobPostingORM

    session = SessionFactory()
    session.add(
        JobPostingORM(
            job_id=job_id,
            title="Engineer",
            company="Acme",
            location="Cairo",
            description="Work.",
            skills=json.dumps(skills),
            source=source,
            url=f"https://example.com/{job_id}",
            date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()
    session.close()


def test_stats_on_an_empty_pool_reports_zero_not_a_placeholder(ctx):
    client, _ = ctx

    body = client.get("/ingestion/stats").json()

    assert body["total_postings"] == 0
    assert body["distinct_tags"] == 0
    assert body["sources"] == []
    assert body["top_tags"] == []
    assert body["last_ingested_at"] is None


def test_stats_counts_postings_sources_and_tags(ctx):
    client, SessionFactory = ctx
    _seed_job(SessionFactory, "a", ["Python", "SQL"])
    _seed_job(SessionFactory, "b", ["python", "docker"])
    _seed_job(SessionFactory, "c", ["SQL"], source="Wuzzuf-Scraper")

    body = client.get("/ingestion/stats").json()

    assert body["total_postings"] == 3
    # Case-folded, so "Python" and "python" are one category rather than two.
    assert body["distinct_tags"] == 3
    assert {s["name"]: s["count"] for s in body["sources"]} == {
        "Arbeitnow": 2,
        "Wuzzuf-Scraper": 1,
    }
    counts = {t["label"]: t["count"] for t in body["top_tags"]}
    assert counts["python"] == 2
    assert counts["sql"] == 2
    assert counts["docker"] == 1


def test_a_tag_repeated_within_one_posting_counts_once(ctx):
    """The number is "postings mentioning X". A source that lists a tag twice
    must not make that category look twice as common as it is."""
    client, SessionFactory = ctx
    _seed_job(SessionFactory, "a", ["Python", "python", "PYTHON"])

    body = client.get("/ingestion/stats").json()

    assert [t["count"] for t in body["top_tags"] if t["label"] == "python"] == [1]


def test_stats_survives_a_malformed_skills_blob(ctx):
    """`skills` is JSON in a TEXT column; one hand-edited row must not take the
    landing page down."""
    client, SessionFactory = ctx
    _seed_job(SessionFactory, "good", ["python"])

    from backend.models.db_models import JobPostingORM

    session = SessionFactory()
    row = session.get(JobPostingORM, "good")
    session.add(
        JobPostingORM(
            job_id="bad",
            title=row.title,
            company=row.company,
            location=row.location,
            description=row.description,
            skills="{not json",
            source="Arbeitnow",
            url="https://example.com/bad",
            date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()
    session.close()

    body = client.get("/ingestion/stats").json()

    assert body["total_postings"] == 2
    assert {t["label"] for t in body["top_tags"]} == {"python"}


def test_top_is_capped_by_the_query_parameter(ctx):
    client, SessionFactory = ctx
    for i in range(8):
        _seed_job(SessionFactory, f"j{i}", [f"tag{i}"])

    body = client.get("/ingestion/stats?top=3").json()

    assert len(body["top_tags"]) == 3
    assert body["distinct_tags"] == 8
