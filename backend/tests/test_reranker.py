"""Tests for the LLM re-ranking stage.

The LLM client is injected, so nothing here touches the network or needs a
key. These pin the defects that made the original `LLM-ranking/backend/LLM.py`
unrunnable, plus the error handling around untrusted model output.
"""

import json

import pytest

from backend.features.ranking.reranker import (
    RETRIEVED_JOB_KEYS,
    RerankError,
    rerank_jobs,
)


class _FakeLLM:
    """Minimal stand-in for the OpenAI client's chat.completions surface."""

    def __init__(self, content: str):
        self._content = content
        self.calls = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                message = type("M", (), {"content": outer._content})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice]})()

        self.chat = type("Chat", (), {"completions": _Completions()})()


def _job(job_id="a1b2c3d4", **overrides):
    fields = dict(
        job_id=job_id,
        title="Backend Engineer",
        company="Acme",
        location="Cairo",
        url=f"https://example.com/jobs/{job_id}",
        source="wuzzuf",
        match_score=0.78,
    )
    fields.update(overrides)
    return fields


def _ranking(job):
    return json.dumps(
        {"top_3": [{"job_id": job["job_id"], "rank": 1, "fit_score": 0.9,
                    "job_data": job}]}
    )


def test_rerank_returns_the_parsed_ranking():
    """The original raised NameError before reaching the LLM at all, because
    the body referenced `m_response` instead of its parameter."""
    job = _job()
    llm = _FakeLLM(_ranking(job))

    result = rerank_jobs(profile={"skills": ["python"]}, jobs=[job], client=llm)

    assert result["top_3"][0]["job_id"] == "a1b2c3d4"
    assert result["top_3"][0]["rank"] == 1


def test_the_jobs_actually_reach_the_prompt():
    """Guards the specific regression: the retrieved jobs must be serialised
    into the user message, not silently dropped."""
    job = _job(title="Data Analyst")
    llm = _FakeLLM(_ranking(job))

    rerank_jobs(profile="a python developer", jobs=[job], client=llm)

    user_message = llm.calls[0]["messages"][1]["content"]
    assert "Data Analyst" in user_message
    assert "a python developer" in user_message


def test_empty_input_short_circuits_without_calling_the_llm():
    llm = _FakeLLM("never used")

    assert rerank_jobs(profile={}, jobs=[], client=llm) == {"top_3": []}
    assert llm.calls == []


def test_markdown_fenced_json_is_still_parsed():
    """Models wrap JSON in ```json fences despite being told not to."""
    job = _job()
    llm = _FakeLLM(f"```json\n{_ranking(job)}\n```")

    result = rerank_jobs(profile={}, jobs=[job], client=llm)

    assert result["top_3"][0]["job_id"] == "a1b2c3d4"


def test_invalid_json_raises_rerank_error():
    """Originally a stray json.loads outside the try/except leaked the raw
    JSONDecodeError instead of the intended error."""
    llm = _FakeLLM("I think the best job is the first one!")

    with pytest.raises(RerankError, match="valid JSON"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)


def test_json_without_top_3_raises_rerank_error():
    llm = _FakeLLM('{"results": []}')

    with pytest.raises(RerankError, match="top_3"):
        rerank_jobs(profile={}, jobs=[_job()], client=llm)


def test_configured_model_is_used_not_a_hardcoded_one(monkeypatch):
    """The original hardcoded model='gpt-5.5', bypassing project config."""
    monkeypatch.setenv("DEFAULT_MODEL", "FW-Kimi-K2.6")
    job = _job()
    llm = _FakeLLM(_ranking(job))

    rerank_jobs(profile={}, jobs=[job], client=llm)

    assert llm.calls[0]["model"] == "FW-Kimi-K2.6"


def test_retrieved_job_keys_match_the_retriever_contract():
    """The prompt promises the model exactly these fields. If the retriever's
    payload changes, this is the test that should fail first."""
    assert set(RETRIEVED_JOB_KEYS) == set(_job().keys())
