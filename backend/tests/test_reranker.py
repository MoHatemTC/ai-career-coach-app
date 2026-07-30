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


def test_default_model_is_not_the_retired_one(monkeypatch):
    """PR #20 hardcoded gemini-1.5-flash, which Google retired: new API keys
    get 404 NOT_FOUND on generateContent. Verified live against a real key."""
    from backend.features.ranking import reranker

    monkeypatch.delenv("RANKING_MODEL", raising=False)

    assert reranker.ranking_model() == "gemini-flash-latest"
    assert reranker.ranking_model() != "gemini-1.5-flash"


def test_ranking_model_is_overridable(monkeypatch):
    from backend.features.ranking import reranker

    monkeypatch.setenv("RANKING_MODEL", "gemini-2.0-flash")

    assert reranker.ranking_model() == "gemini-2.0-flash"


def test_configured_model_reaches_the_api_call(monkeypatch):
    monkeypatch.setenv("RANKING_MODEL", "gemini-2.0-flash")
    job = _job()
    llm = _FakeGemini(_ranking(_entry(job)))

    rerank_jobs(profile={}, jobs=[job], client=llm)

    assert llm.calls[0]["model"] == "gemini-2.0-flash"


def test_unavailable_model_gives_actionable_error():
    """A bare 404 reads like the service is down rather than a config problem."""
    class _Boom:
        class _Models:
            def generate_content(self, **kwargs):
                raise RuntimeError(
                    "404 NOT_FOUND. models/gemini-1.5-flash is not found for "
                    "API version v1beta"
                )

        models = _Models()

    with pytest.raises(RerankError, match="RANKING_MODEL"):
        rerank_jobs(profile={}, jobs=[_job()], client=_Boom())


def test_retrieved_job_keys_match_the_retriever_contract():
    """If the retriever's payload changes, this should fail first."""
    assert set(RETRIEVED_JOB_KEYS) == set(_job().keys())


class _FlakyGemini:
    """Fails with a transient error N times, then succeeds."""

    def __init__(self, text, failures, message="503 UNAVAILABLE high demand"):
        self.attempts = 0
        outer = self

        class _Models:
            def generate_content(self, **kwargs):
                outer.attempts += 1
                if outer.attempts <= failures:
                    raise RuntimeError(message)
                return type("R", (), {"text": text})()

        self.models = _Models()


def test_transient_overload_is_retried(monkeypatch):
    """Gemini returns 503 'experiencing high demand' under load. Failing the
    user's request over a momentary capacity spike is the wrong trade."""
    monkeypatch.setattr(
        "backend.features.ranking.reranker.RETRY_BACKOFF_SECONDS", 0
    )
    job = _job()
    llm = _FlakyGemini(_ranking(_entry(job)), failures=2)

    result = rerank_jobs(profile={}, jobs=[job], client=llm)

    assert llm.attempts == 3
    assert result["top_3"][0]["job_id"] == "a1"


def test_persistent_overload_gives_a_try_again_error(monkeypatch):
    monkeypatch.setattr(
        "backend.features.ranking.reranker.RETRY_BACKOFF_SECONDS", 0
    )
    llm = _FlakyGemini("never reached", failures=99)

    with pytest.raises(RerankError, match="temporary"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)


def test_a_404_is_not_retried(monkeypatch):
    """A retired model is a config problem; retrying it just wastes time."""
    monkeypatch.setattr(
        "backend.features.ranking.reranker.RETRY_BACKOFF_SECONDS", 0
    )
    llm = _FlakyGemini("x", failures=99, message="404 NOT_FOUND model gone")

    with pytest.raises(RerankError, match="RANKING_MODEL"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)

    assert llm.attempts == 1


def test_a_real_bug_is_not_retried(monkeypatch):
    """Only transient errors retry; a genuine fault must surface immediately."""
    monkeypatch.setattr(
        "backend.features.ranking.reranker.RETRY_BACKOFF_SECONDS", 0
    )
    llm = _FlakyGemini("x", failures=99, message="TypeError: bad argument")

    with pytest.raises(RuntimeError, match="bad argument"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)

    assert llm.attempts == 1


def test_ranking_model_actually_reaches_the_provider(monkeypatch):
    """RANKING_MODEL was read and then never passed to the call, so setting it
    did nothing at all. A config knob that silently does nothing is worse than
    no knob."""
    from backend.features.ranking import reranker

    captured = {}

    def _complete(prompt, model=None, **kwargs):
        captured["model"] = model
        return _ranking(_entry(_job()))

    monkeypatch.setenv("RANKING_MODEL", "some-specific-model")
    monkeypatch.setattr("backend.services.llm_client.complete", _complete)

    reranker.rerank_jobs(profile={}, jobs=[_job()])

    assert captured["model"] == "some-specific-model"


def test_unset_ranking_model_defers_to_the_provider(monkeypatch):
    """Unset must mean None, not a Gemini model id: sending gemini-flash-latest
    to the LiteLLM gateway would ask it for a model it does not serve."""
    from backend.features.ranking import reranker

    captured = {}

    def _complete(prompt, model=None, **kwargs):
        captured["model"] = model
        return _ranking(_entry(_job()))

    monkeypatch.delenv("RANKING_MODEL", raising=False)
    monkeypatch.setattr("backend.services.llm_client.complete", _complete)

    reranker.rerank_jobs(profile={}, jobs=[_job()])

    assert captured["model"] is None


def test_provider_returning_nothing_is_an_actionable_error(monkeypatch):
    from backend.features.ranking import reranker

    monkeypatch.setattr(
        "backend.services.llm_client.complete", lambda *a, **k: None
    )

    with pytest.raises(RerankError, match="AI_PROVIDER"):
        reranker.rerank_jobs(profile={}, jobs=[_job()])
