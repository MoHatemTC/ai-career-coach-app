"""Tests for stage 3 of the pipeline: explaining each ranked job.

Uses a real in-memory SQLite database and the real skill-gap analyser. Only
Gemini is substituted, via the agent's own documented fallback path, so these
run offline.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db_models import Base, job_posting_to_orm
from backend.models.job import JobPosting
from backend.services import matching_pipeline
from backend.services.matching_pipeline import (
    attach_explanations,
    build_profile,
    explain_ranked_job,
)

UI_PROFILE = {
    "title": "Backend Developer",
    "skills": ["python", "sql"],
    "experience": "Built REST APIs",
}


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    yield db
    db.close()


def _posting(job_id="a1", skills=("python", "kubernetes")) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        title="Backend Engineer",
        company="Acme",
        location="Cairo",
        description="Build APIs.",
        skills=list(skills),
        source="wuzzuf",
        url=f"https://example.com/{job_id}",
        date=datetime.now(timezone.utc),
    )


def _entry(job_id="a1", fit=0.9):
    return {
        "job_id": job_id,
        "rank": 1,
        "fit_score": fit,
        "job_data": {"job_id": job_id, "title": "Backend Engineer"},
    }


def _seed(session, posting):
    session.add(job_posting_to_orm(posting))
    session.commit()


# --- build_profile -----------------------------------------------------------


def test_ui_title_maps_to_target_role():
    """The CV parser says 'title'; Profile says 'target_role'. Neither lane
    should have to rename its field, so the mapping lives in the pipeline."""
    assert build_profile(UI_PROFILE).target_role == "Backend Developer"


def test_profile_skills_survive_both_shapes():
    assert build_profile({"skills": ["python"]}).skills == ["python"]
    assert build_profile({"skills": "python, sql"}).skills == ["python", "sql"]


def test_profile_defaults_user_id():
    assert build_profile({}).user_id == "default"


# --- explain_ranked_job ------------------------------------------------------


def test_explanation_has_the_contract_keys(session):
    _seed(session, _posting())

    explanation = explain_ranked_job(_entry(), build_profile(UI_PROFILE), session)

    assert set(explanation) == {
        "overall_alignment_summary",
        "strengths",
        "gaps_or_missing_requirements",
        "recommendations",
        "next_steps",
    }


def test_missing_posting_yields_no_explanation(session):
    """Qdrant and SQLite can drift. Explaining a job we cannot look up would
    mean inventing its requirements, so it is skipped."""
    explanation = explain_ranked_job(
        _entry(job_id="not-in-db"), build_profile(UI_PROFILE), session
    )

    assert explanation is None


def test_skill_gap_feeds_the_agent(session, monkeypatch):
    """The agent explains an already-computed match. The matched and missing
    skills must come from the analyser, not be re-derived by the agent."""
    _seed(session, _posting(skills=["python", "kubernetes"]))
    captured = {}

    def _spy(profile, job, match_result, **kwargs):
        captured["match_result"] = match_result
        captured["job"] = job
        from backend.services.match_explanation_agent import MatchExplanation

        return MatchExplanation()

    monkeypatch.setattr(matching_pipeline, "generate_match_explanation", _spy)

    explain_ranked_job(_entry(), build_profile(UI_PROFILE), session)

    result = captured["match_result"]
    assert "python" in [s.lower() for s in result.matched_skills]
    assert "kubernetes" in [s.lower() for s in result.missing_skills]
    # The job's required skills reach the agent via JobInfo.
    assert captured["job"].required_skills == ["python", "kubernetes"]


def test_fit_score_is_passed_through_not_recomputed(session, monkeypatch):
    """The re-ranker owns the score; the agent explains it verbatim."""
    _seed(session, _posting())
    captured = {}

    def _spy(profile, job, match_result, **kwargs):
        captured["score"] = match_result.match_score
        from backend.services.match_explanation_agent import MatchExplanation

        return MatchExplanation()

    monkeypatch.setattr(matching_pipeline, "generate_match_explanation", _spy)

    explain_ranked_job(_entry(fit=0.91), build_profile(UI_PROFILE), session)

    assert captured["score"] == pytest.approx(91.0)


# --- attach_explanations -----------------------------------------------------


def test_attach_adds_explanation_to_each_entry(session):
    _seed(session, _posting("a1"))
    _seed(session, _posting("b2"))
    ranked = [_entry("a1"), _entry("b2")]

    attach_explanations(ranked, UI_PROFILE, session)

    assert all("explanation" in entry for entry in ranked)


def test_one_failure_does_not_lose_the_other_results(session, monkeypatch):
    """A single job failing to explain must not empty the whole result set."""
    _seed(session, _posting("a1"))
    _seed(session, _posting("b2"))
    calls = {"n": 0}

    real = matching_pipeline.explain_ranked_job

    def _flaky(entry, profile, sess):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(entry, profile, sess)

    monkeypatch.setattr(matching_pipeline, "explain_ranked_job", _flaky)
    ranked = [_entry("a1"), _entry("b2")]

    attach_explanations(ranked, UI_PROFILE, session)

    assert "explanation" not in ranked[0]
    assert "explanation" in ranked[1]


def test_pipeline_skips_explanations_without_a_session(monkeypatch):
    """Retrieval and ranking stay usable on their own."""
    job = {
        "job_id": "a1", "title": "T", "company": "C", "location": "L",
        "url": "https://x", "source": "s", "match_score": 0.7,
    }
    monkeypatch.setattr(
        matching_pipeline, "retrieve_top_jobs", lambda cv_text, top_k: [job]
    )
    monkeypatch.setattr(
        matching_pipeline, "rerank_jobs",
        lambda profile, jobs, client=None: {"top_3": [_entry()]},
    )

    ranked = matching_pipeline.run_match_pipeline(UI_PROFILE, session=None)

    assert ranked and "explanation" not in ranked[0]


def test_job_data_is_enriched_for_the_card(session):
    """The plan's rendered match shows location, description and required
    skills. The Qdrant payload carries none of those, but the SQLite join in
    this stage already has the full posting, so the entry is enriched rather
    than the UI fetching it again at display time."""
    _seed(session, _posting(skills=["python", "kubernetes"]))
    entry = _entry()

    explain_ranked_job(entry, build_profile(UI_PROFILE), session)

    job_data = entry["job_data"]
    assert job_data["location"] == "Cairo"
    assert job_data["description"] == "Build APIs."
    assert job_data["required_skills"] == ["python", "kubernetes"]
    assert job_data["date_posted"]


def test_enrichment_does_not_clobber_a_payload_location(session):
    """Qdrant's own location wins if it is already there; the join only fills
    what the payload lacks."""
    _seed(session, _posting())
    entry = _entry()
    entry["job_data"]["location"] = "Remote"

    explain_ranked_job(entry, build_profile(UI_PROFILE), session)

    assert entry["job_data"]["location"] == "Remote"
