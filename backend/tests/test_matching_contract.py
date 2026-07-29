"""Regression tests for the matching lane's wiring to the vector store.

These pin the two defects that made `main` unusable: a missing module that
broke `import backend.main` outright, and a scorer reading a field that the
object it is actually passed does not have.
"""

import inspect

import pytest

from backend.features.matching import vector_store
from backend.features.matching.retriever import retrieve_top_jobs
from backend.features.matching.scorer import calculate_match_score
from backend.models.job import JobPosting
from backend.models.profile import Profile


def _job(**overrides) -> JobPosting:
    fields = dict(
        job_id="abc123",
        title="Backend Engineer",
        company="Acme",
        location="Cairo",
        description="Build APIs.",
        skills=["python", "fastapi"],
        source="mock_mena",
        url="https://example.com/jobs/1",
        date="2026-01-01T00:00:00",
    )
    fields.update(overrides)
    return JobPosting(**fields)


def _profile(**overrides) -> Profile:
    # Profile is the skill-gap lane's dataclass: user_id / skills /
    # target_role / experience_level.
    fields = dict(
        user_id="u1",
        skills=["python"],
        target_role="Backend Developer",
        experience_level="junior",
    )
    fields.update(overrides)
    return Profile(**fields)


def test_embedding_contract_constants_are_frozen():
    """The ingestion lane writes this collection and the matching lane reads
    it. If these drift apart, similarity search silently returns nonsense
    instead of failing loudly — so they are pinned here."""
    assert vector_store.COLLECTION_NAME == "job_postings"
    assert vector_store.EMBEDDING_MODEL_NAME == "all-MiniLM-L6-v2"
    assert vector_store.VECTOR_SIZE == 384


def test_scorer_reads_the_canonical_job_schema():
    """`routes.py` scores the output of `orm_to_job_posting`, which is the
    canonical `models.job.JobPosting` (field: `skills`). The scorer used to
    read `required_skills` from a second, forked schema and raised
    AttributeError on every request that reached it.

    An empty profile short-circuits before any embedding, so this asserts the
    attribute access without loading the model.
    """
    score = calculate_match_score(_profile(skills=[]), _job())
    assert score == 0.0


def test_retriever_signature_matches_its_caller():
    """`routes.py` used to pass `db=`; the retriever queries Qdrant and takes
    no session, so the call raised TypeError — which the caller's bare
    `except Exception` swallowed, silently disabling the whole RAG path."""
    sig = inspect.signature(retrieve_top_jobs)
    assert "db" not in sig.parameters
    sig.bind(cv_text="python developer", top_k=5)


def test_retriever_call_with_db_kwarg_is_rejected():
    """Guards the specific regression: reintroducing `db=` must fail fast."""
    with pytest.raises(TypeError):
        inspect.signature(retrieve_top_jobs).bind(cv_text="x", db=object(), top_k=5)
