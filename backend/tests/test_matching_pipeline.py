"""Tests for the retrieve -> re-rank pipeline and its HTTP endpoint.

Both the retriever and the LLM are substituted, so nothing here touches Qdrant,
the network, or a model.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import matching_pipeline
from backend.services.matching_pipeline import profile_to_text, run_match_pipeline

UI_PROFILE = {
    "name": "Omar",
    "title": "Backend Developer",
    "skills": ["python", "fastapi"],
    "experience": ["Built an ingestion pipeline"],
    "education": "BSc Computer Science",
}


def _retrieved(job_id="a1", **overrides):
    fields = dict(
        job_id=job_id,
        title="Backend Engineer",
        company="Acme",
        location="Cairo",
        url=f"https://example.com/{job_id}",
        source="wuzzuf",
        match_score=0.78,
    )
    fields.update(overrides)
    return fields


class _FakeLLM:
    """Stand-in for genai.Client(); returns a fixed ranking, records calls."""

    def __init__(self, content):
        self.calls = []
        outer = self

        class _Models:
            def generate_content(self, **kwargs):
                outer.calls.append(kwargs)
                return type("R", (), {"text": content})()

        self.models = _Models()


def _ranking_json(job):
    import json

    return json.dumps(
        {"top_3": [{"job_id": job["job_id"], "rank": 1, "fit_score": 0.9,
                    "job_data": job}]}
    )


# --- profile_to_text ---------------------------------------------------------


def test_profile_text_includes_skills_and_free_text():
    text = profile_to_text(UI_PROFILE)

    assert "Backend Developer" in text
    assert "Skills: python, fastapi" in text
    assert "ingestion pipeline" in text


def test_profile_text_labels_skills_like_the_indexed_text():
    """The job side of the collection labels skills under 'Skills:' (see
    docs/vector-store.md). Query text that mirrors it retrieves better."""
    assert "Skills: python, fastapi" in profile_to_text(UI_PROFILE)


def test_profile_text_accepts_both_title_spellings():
    """The CV parser says 'title', backend.models.profile says
    'current_title'. Neither lane should have to rename its field."""
    assert "Data Analyst" in profile_to_text({"current_title": "Data Analyst"})
    assert "Data Analyst" in profile_to_text({"title": "Data Analyst"})


def test_empty_profile_produces_empty_text():
    assert profile_to_text({}) == ""
    assert profile_to_text({"name": "Omar"}) == ""  # name alone is not signal


# --- run_match_pipeline ------------------------------------------------------


def test_pipeline_retrieves_then_reranks(monkeypatch):
    job = _retrieved()
    monkeypatch.setattr(
        matching_pipeline, "retrieve_top_jobs", lambda cv_text, top_k: [job]
    )
    llm = _FakeLLM(_ranking_json(job))

    ranked = run_match_pipeline(UI_PROFILE, llm_client=llm)

    assert len(ranked) == 1
    assert ranked[0]["job_data"]["title"] == "Backend Engineer"
    assert ranked[0]["rank"] == 1


def test_pipeline_skips_the_llm_when_retrieval_finds_nothing(monkeypatch):
    """An empty collection should not cost an LLM call."""
    monkeypatch.setattr(
        matching_pipeline, "retrieve_top_jobs", lambda cv_text, top_k: []
    )
    llm = _FakeLLM("never used")

    assert run_match_pipeline(UI_PROFILE, llm_client=llm) == []
    assert llm.calls == []


def test_pipeline_skips_retrieval_for_an_empty_profile(monkeypatch):
    called = []
    monkeypatch.setattr(
        matching_pipeline,
        "retrieve_top_jobs",
        lambda cv_text, top_k: called.append(cv_text) or [],
    )

    assert run_match_pipeline({}, llm_client=_FakeLLM("x")) == []
    assert called == []


def test_top_k_is_retrieval_width_not_output_size(monkeypatch):
    job = _retrieved()
    seen = {}
    monkeypatch.setattr(
        matching_pipeline,
        "retrieve_top_jobs",
        lambda cv_text, top_k: seen.update(top_k=top_k) or [job],
    )

    ranked = run_match_pipeline(UI_PROFILE, top_k=25, llm_client=_FakeLLM(_ranking_json(job)))

    assert seen["top_k"] == 25
    assert len(ranked) == 1  # the re-ranker narrows, not top_k


def test_retrieval_failure_propagates(monkeypatch):
    """A locked or unreachable Qdrant must not look like 'no matches'."""
    def _boom(cv_text, top_k):
        raise RuntimeError("Storage folder is already accessed by another instance")

    monkeypatch.setattr(matching_pipeline, "retrieve_top_jobs", _boom)

    with pytest.raises(RuntimeError, match="already accessed"):
        run_match_pipeline(UI_PROFILE, llm_client=_FakeLLM("x"))


# --- the HTTP endpoint -------------------------------------------------------


@pytest.fixture
def client():
    from backend.features.matching.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/matching")
    return TestClient(app)


def test_endpoint_returns_the_ranking(client, monkeypatch):
    job = _retrieved()
    monkeypatch.setattr(
        matching_pipeline, "retrieve_top_jobs", lambda cv_text, top_k: [job]
    )
    monkeypatch.setattr(
        matching_pipeline, "rerank_jobs",
        lambda profile, jobs, client=None: {
            "top_3": [{"job_id": "a1", "rank": 1, "fit_score": 0.9, "job_data": job}]
        },
    )

    response = client.post("/matching/pipeline", json={"profile": UI_PROFILE})

    assert response.status_code == 200
    assert response.json()["ranked"][0]["job_data"]["company"] == "Acme"


def test_endpoint_reports_pipeline_failure_as_503(client, monkeypatch):
    """The UI distinguishes 'nothing matched' from 'the pipeline is down'."""
    def _boom(cv_text, top_k):
        raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr(matching_pipeline, "retrieve_top_jobs", _boom)

    response = client.post("/matching/pipeline", json={"profile": UI_PROFILE})

    assert response.status_code == 503
    assert "qdrant unreachable" in response.json()["detail"]
