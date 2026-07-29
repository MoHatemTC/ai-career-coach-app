"""Tests for the LLM re-ranking stage.

The Gemini client is injected, so nothing here touches the network or needs a
key. Covers the contract of Ramez's ranking logic (PR #20) plus the
integration guards added when it moved into the backend package.
"""

import json

import pytest

from backend.features.ranking.reranker import (
    RETRIEVED_JOB_KEYS,
    RerankError,
    create_llm,
    rerank_jobs,
)


class _FakeGemini:
    """Stand-in for genai.Client()'s models.generate_content surface."""

    def __init__(self, text: str):
        self.calls = []
        outer = self

        class _Models:
            def generate_content(self, **kwargs):
                outer.calls.append(kwargs)
                return type("R", (), {"text": text})()

        self.models = _Models()


def _job(job_id="a1", **overrides):
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


def _ranking(*entries):
    return json.dumps({"top_3": list(entries)})


def _entry(job, rank=1, fit=0.9, job_data=None):
    return {
        "job_id": job["job_id"],
        "rank": rank,
        "fit_score": fit,
        "job_data": job_data if job_data is not None else job,
    }


def test_rerank_returns_the_parsed_ranking():
    job = _job()
    llm = _FakeGemini(_ranking(_entry(job)))

    result = rerank_jobs(profile={"skills": ["python"]}, jobs=[job], client=llm)

    assert result["top_3"][0]["job_id"] == "a1"
    assert result["top_3"][0]["rank"] == 1
    assert result["top_3"][0]["fit_score"] == 0.9


def test_the_jobs_actually_reach_the_prompt():
    job = _job(title="Data Analyst")
    llm = _FakeGemini(_ranking(_entry(job)))

    rerank_jobs(profile="a python developer", jobs=[job], client=llm)

    text = llm.calls[0]["contents"][0]["parts"][0]["text"]
    assert "Data Analyst" in text
    assert "a python developer" in text


def test_json_mime_type_is_requested():
    """Ramez's call asks Gemini for JSON directly; keep that."""
    job = _job()
    llm = _FakeGemini(_ranking(_entry(job)))

    rerank_jobs(profile={}, jobs=[job], client=llm)

    assert llm.calls[0]["config"]["response_mime_type"] == "application/json"


def test_empty_input_short_circuits_without_calling_the_llm():
    llm = _FakeGemini("never used")

    assert rerank_jobs(profile={}, jobs=[], client=llm) == {"top_3": []}
    assert llm.calls == []


def test_invented_job_data_is_replaced_with_the_real_posting():
    """The model is asked to echo job data back, and models paraphrase and
    invent when they do. The retrieved posting is authoritative."""
    job = _job()
    hallucinated = dict(job, company="Totally Different Corp", salary_range="9000-13000")
    llm = _FakeGemini(_ranking(_entry(job, job_data=hallucinated)))

    result = rerank_jobs(profile={}, jobs=[job], client=llm)

    assert result["top_3"][0]["job_data"] == job
    assert result["top_3"][0]["job_data"]["company"] == "Acme"
    assert "salary_range" not in result["top_3"][0]["job_data"]


def test_a_wholly_invented_job_is_dropped():
    """A job_id that was never retrieved cannot reach the UI."""
    job = _job()
    ghost = _job(job_id="does-not-exist", title="Dream Job")
    llm = _FakeGemini(_ranking(_entry(job), _entry(ghost, rank=2)))

    result = rerank_jobs(profile={}, jobs=[job], client=llm)

    assert [e["job_id"] for e in result["top_3"]] == ["a1"]


def test_the_models_ranking_is_preserved():
    """Reconciliation must not flatten rank/fit_score — those are the model's
    actual contribution."""
    first, second = _job("a1"), _job("b2")
    llm = _FakeGemini(
        _ranking(_entry(second, rank=1, fit=0.95), _entry(first, rank=2, fit=0.4))
    )

    result = rerank_jobs(profile={}, jobs=[first, second], client=llm)

    assert [e["job_id"] for e in result["top_3"]] == ["b2", "a1"]
    assert result["top_3"][0]["fit_score"] == 0.95


def test_invalid_json_raises_rerank_error():
    llm = _FakeGemini("I think the best job is the first one!")

    with pytest.raises(RerankError, match="valid JSON"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)


def test_json_without_top_3_raises_rerank_error():
    llm = _FakeGemini('{"results": []}')

    with pytest.raises(RerankError, match="top_3"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)


def test_create_llm_alias_still_works():
    """Ramez's lane calls it create_llm; that name must keep working."""
    job = _job()
    llm = _FakeGemini(_ranking(_entry(job)))

    assert create_llm({}, [job], client=llm)["top_3"][0]["job_id"] == "a1"


def test_retrieved_job_keys_match_the_retriever_contract():
    """If the retriever's payload changes, this should fail first."""
    assert set(RETRIEVED_JOB_KEYS) == set(_job().keys())
