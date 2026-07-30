"""Tests for backend/services/match_explanation_agent.py.

Covers:
- MatchExplanation schema validation.
- Deterministic fallback when Gemini is unavailable or returns
  malformed/invalid JSON - built only from match_result, never invents
  data or changes the score.
- generate_match_explanation happy path (mocked call_gemini), and the
  retry-once-on-invalid-JSON behavior.
- ContextStore abstraction: InMemoryContextStore satisfies it, and
  AgentContextStore remains a working backward-compatible alias.
- AgentContext creation and the get_or_create_explanation cache: a
  second call for the same candidate/job pair must NOT call Gemini
  again (cache hit), an unseen pair must (cache miss), and an invalid
  cached context (mismatched ids / missing explanation / missing
  score) must be treated as a miss and regenerated.
- load_context() as a pure lookup.
- answer_followup_question happy path + fallback, and that it never
  re-runs Skill Gap analysis or the matching engine (it only ever
  touches the AgentContext already provided).

These tests never call the real Gemini API - `call_gemini` is mocked
throughout.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.models.agent_context import (
    AgentContext,
    AgentContextStore,
    ContextStore,
    CURRENT_CONTEXT_VERSION,
    InMemoryContextStore,
)
from backend.models.job import JobInfo
from backend.models.match_result import MatchResult
from backend.models.profile import Profile
from backend.services.match_explanation_agent import (
    MatchExplanation,
    MatchExplanationAgent,
    _context_matches_match_result,
    _fallback_explanation,
    _is_explanation_consistent_with_score,
    _is_valid_cached_context,
    answer_followup_question,
    build_agent_context,
    generate_match_explanation,
    get_or_create_explanation,
    invalidate_context,
    load_context,
)


def _sample_profile() -> Profile:
    return Profile(
        user_id="cand-1",
        skills=["Python", "FastAPI", "Docker"],
        target_role="Backend Developer",
        experience_level="junior",
    )


def _sample_job() -> JobInfo:
    return JobInfo(
        job_id="job-1",
        title="Backend Developer",
        company="Acme Corp",
        required_skills=["Python", "REST APIs", "Docker", "PostgreSQL"],
    )


def _sample_match_result() -> MatchResult:
    return MatchResult(
        match_score=82.0,
        matched_skills=["Python", "Docker"],
        missing_skills=["REST APIs", "PostgreSQL"],
    )


# ---------------------------------------------------------------------------
# MatchExplanation schema
# ---------------------------------------------------------------------------


class TestMatchExplanationSchema:
    def test_accepts_a_fully_populated_valid_response(self):
        data = {
            "overall_alignment_summary": "Strong candidate with a couple of gaps.",
            "strengths": ["Solid Python and Docker experience."],
            "gaps_or_missing_requirements": ["No REST API experience listed."],
            "recommendations": ["Highlight any API work you've done."],
            "next_steps": ["Apply, and mention your Docker projects."],
        }
        explanation = MatchExplanation.model_validate(data)
        assert explanation.overall_alignment_summary == data["overall_alignment_summary"]
        assert explanation.strengths == data["strengths"]

    def test_defaults_to_empty_when_fields_missing(self):
        explanation = MatchExplanation.model_validate({})
        assert explanation.overall_alignment_summary == ""
        assert explanation.strengths == []
        assert explanation.gaps_or_missing_requirements == []
        assert explanation.recommendations == []
        assert explanation.next_steps == []


# ---------------------------------------------------------------------------
# Deterministic fallback - never invents data, never changes the score
# ---------------------------------------------------------------------------


class TestFallbackExplanation:
    def test_fallback_uses_only_match_result_data(self):
        match_result = _sample_match_result()
        explanation = _fallback_explanation(match_result)

        assert "82" in explanation.overall_alignment_summary
        assert explanation.strengths == match_result.matched_skills
        assert explanation.gaps_or_missing_requirements == match_result.missing_skills
        # Never invents a skill not present in the match result.
        for rec in explanation.recommendations:
            assert any(skill in rec for skill in match_result.missing_skills)

    def test_fallback_with_no_missing_skills_recommends_applying(self):
        match_result = MatchResult(match_score=100.0, matched_skills=["Python"], missing_skills=[])
        explanation = _fallback_explanation(match_result)
        assert explanation.recommendations == []
        assert any("applying" in step.lower() for step in explanation.next_steps)


# ---------------------------------------------------------------------------
# generate_match_explanation - mocked Gemini
# ---------------------------------------------------------------------------


class TestGenerateMatchExplanation:
    def test_happy_path_returns_validated_explanation(self):
        payload = (
            '{"overall_alignment_summary": "Good fit overall.",'
            ' "strengths": ["Python"],'
            ' "gaps_or_missing_requirements": ["REST APIs"],'
            ' "recommendations": ["Learn REST APIs"],'
            ' "next_steps": ["Apply"]}'
        )
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=payload,
        ) as mock_call:
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        mock_call.assert_called_once()
        assert explanation.overall_alignment_summary == "Good fit overall."
        assert explanation.strengths == ["Python"]

    def test_falls_back_when_gemini_unavailable(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=None,
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert explanation.strengths == _sample_match_result().matched_skills

    def test_falls_back_on_malformed_json_after_retrying_once(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="not json {{{",
        ) as mock_call:
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        # One initial attempt + one retry, both invalid -> fallback.
        assert mock_call.call_count == 2
        assert explanation.strengths == _sample_match_result().matched_skills

    def test_falls_back_on_schema_violation_after_retrying_once(self):
        # strengths must be a list of strings - a dict is invalid.
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"strengths": {"not": "a list"}}',
        ) as mock_call:
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert mock_call.call_count == 2
        assert explanation.strengths == _sample_match_result().matched_skills

    def test_retry_succeeds_after_an_initial_invalid_response(self):
        # First call returns garbage, second (the retry) returns valid JSON -
        # the agent should use the retry's result, not fall back.
        responses = iter(["not json {{{", '{"overall_alignment_summary": "recovered"}'])

        def _side_effect(prompt, model=None, api_key=None, **kwargs):
            return next(responses)

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            side_effect=_side_effect,
        ) as mock_call:
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert mock_call.call_count == 2
        assert explanation.overall_alignment_summary == "recovered"

    def test_falls_back_when_gemini_unavailable_on_retry(self):
        # First call returns invalid JSON, retry call returns None
        # (Gemini became unavailable) - should still fall back gracefully.
        responses = iter(["not json {{{", None])

        def _side_effect(prompt, model=None, api_key=None, **kwargs):
            return next(responses)

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            side_effect=_side_effect,
        ) as mock_call:
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert mock_call.call_count == 2
        assert explanation.strengths == _sample_match_result().matched_skills

    def test_fallback_after_retry_still_respects_the_response_schema(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="not json {{{",
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        # The fallback is still a valid MatchExplanation, not a bare dict
        # or an ad-hoc structure - same schema every caller can rely on.
        assert isinstance(explanation, MatchExplanation)
        assert isinstance(explanation.strengths, list)
        assert isinstance(explanation.gaps_or_missing_requirements, list)
        assert isinstance(explanation.recommendations, list)
        assert isinstance(explanation.next_steps, list)

    def test_strips_markdown_code_fences(self):
        payload = '```json\n{"overall_alignment_summary": "fenced"}\n```'
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=payload,
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert explanation.overall_alignment_summary == "fenced"

    def test_never_recalculates_or_reads_score_from_gemini_response(self):
        # Even if Gemini's response contained a "match_score" field, the
        # agent's schema has no such field - it can never leak into the
        # explanation or override match_result.match_score.
        payload = '{"overall_alignment_summary": "ok", "match_score": 999}'
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=payload,
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert not hasattr(explanation, "match_score")


# ---------------------------------------------------------------------------
# build_agent_context
# ---------------------------------------------------------------------------


class TestBuildAgentContext:
    def test_context_carries_match_result_fields_unchanged(self):
        match_result = _sample_match_result()
        explanation = MatchExplanation(overall_alignment_summary="ok")

        context = build_agent_context("cand-1", "job-1", match_result, explanation)

        assert context.candidate_id == "cand-1"
        assert context.job_id == "job-1"
        assert context.match_score == match_result.match_score
        assert context.matched_skills == match_result.matched_skills
        assert context.missing_skills == match_result.missing_skills
        assert context.explanation["overall_alignment_summary"] == "ok"


# ---------------------------------------------------------------------------
# get_or_create_explanation - caching / no duplicate Gemini calls
# ---------------------------------------------------------------------------


class TestGetOrCreateExplanation:
    def test_cache_miss_generates_and_caches(self):
        store = AgentContextStore()
        payload = '{"overall_alignment_summary": "first"}'

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=payload,
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "first"
        assert store.load("cand-1", "job-1") is context

    def test_cache_hit_reuses_context_without_calling_gemini(self):
        store = AgentContextStore()
        payload = '{"overall_alignment_summary": "first"}'

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=payload,
        ) as mock_call:
            first = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            side_effect=AssertionError("Gemini should not be called again"),
        ):
            second = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        assert first is second
        assert mock_call.call_count == 1

    def test_different_job_id_is_a_cache_miss_and_generates_a_separate_context(self):
        store = AgentContextStore()
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "x"}',
        ):
            get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )
            get_or_create_explanation(
                "cand-1", "job-2", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        assert store.load("cand-1", "job-1") is not store.load("cand-1", "job-2")

    def test_invalid_cached_context_missing_explanation_is_regenerated(self):
        store = AgentContextStore()
        # Simulate a corrupted/stale cache entry: right ids, but no
        # explanation content.
        store.save(
            AgentContext(
                candidate_id="cand-1", job_id="job-1", match_score=82.0, explanation={}
            )
        )

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "regenerated"}',
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "regenerated"

    def test_invalid_cached_context_missing_score_is_regenerated(self):
        store = AgentContextStore()
        stale = AgentContext(
            candidate_id="cand-1",
            job_id="job-1",
            match_score=82.0,
            explanation={"overall_alignment_summary": "stale"},
        )
        stale.match_score = None  # simulate a corrupted record
        store.save(stale)

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "regenerated"}',
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "regenerated"

    def test_invalid_cached_context_mismatched_ids_is_regenerated(self):
        store = AgentContextStore()
        # Simulate a store bug: entry stored under the right key but
        # carrying different candidate/job ids internally.
        store.save(
            AgentContext(
                candidate_id="someone-else",
                job_id="job-1",
                match_score=82.0,
                explanation={"overall_alignment_summary": "not this candidate"},
            )
        )
        # Force it under the (cand-1, job-1) key directly to simulate the
        # mismatch scenario without relying on save()'s own keying.
        store._contexts[("cand-1", "job-1")] = store.load("someone-else", "job-1")

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "regenerated"}',
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "regenerated"


class TestContextMatchesMatchResult:
    def test_matches_when_score_and_skills_are_identical(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            matched_skills=["Python"], missing_skills=["Docker"],
            explanation={"a": "b"},
        )
        current = MatchResult(match_score=82.0, matched_skills=["Python"], missing_skills=["Docker"])
        assert _context_matches_match_result(context, current) is True

    def test_does_not_match_when_score_changed(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            matched_skills=["Python"], missing_skills=["Docker"],
        )
        current = MatchResult(match_score=55.0, matched_skills=["Python"], missing_skills=["Docker"])
        assert _context_matches_match_result(context, current) is False

    def test_does_not_match_when_skills_changed(self):
        # Simulates a new CV upload for the same candidate_id/job_id:
        # the ids are unchanged but the underlying skills are different.
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            matched_skills=["Python"], missing_skills=["Docker"],
        )
        current = MatchResult(
            match_score=82.0, matched_skills=["Python", "Docker"], missing_skills=[]
        )
        assert _context_matches_match_result(context, current) is False


class TestGetOrCreateExplanationCallsGeminiOnlyWhenNecessary:
    def test_stale_cache_from_new_cv_upload_triggers_regeneration(self):
        # Same candidate_id/job_id, but the match_result reflects a new
        # CV upload (different matched/missing skills) - must NOT reuse
        # the stale cached explanation.
        store = AgentContextStore()
        old_match_result = MatchResult(
            match_score=60.0, matched_skills=["Python"], missing_skills=["Docker", "SQL"]
        )
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "old CV"}',
        ):
            get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                old_match_result, store=store,
            )

        new_match_result = MatchResult(
            match_score=90.0, matched_skills=["Python", "Docker", "SQL"], missing_skills=[]
        )
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "new CV"}',
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                new_match_result, store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "new CV"
        assert context.matched_skills == ["Python", "Docker", "SQL"]

    def test_unchanged_match_result_never_calls_gemini_again(self):
        store = AgentContextStore()
        match_result = _sample_match_result()

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "stable"}',
        ) as mock_call:
            first = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                match_result, store=store,
            )
            second = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                match_result, store=store,
            )

        assert first is second
        mock_call.assert_called_once()

    def test_cache_miss_is_the_only_reason_gemini_is_called_on_first_request(self):
        store = AgentContextStore()
        assert store.exists("cand-1", "job-1") is False

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "generated"}',
        ) as mock_call:
            get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()


class TestInvalidateContext:
    def test_removes_cached_context_via_store_delete(self):
        store = AgentContextStore()
        store.save(
            AgentContext(candidate_id="cand-1", job_id="job-1", match_score=82.0)
        )

        invalidate_context("cand-1", "job-1", store=store)

        assert store.exists("cand-1", "job-1") is False

    def test_forces_regeneration_on_next_get_or_create_explanation_call(self):
        store = AgentContextStore()
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "first"}',
        ):
            get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        invalidate_context("cand-1", "job-1", store=store)

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "regenerated after invalidate"}',
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "regenerated after invalidate"

    def test_is_a_no_op_when_nothing_cached(self):
        store = AgentContextStore()
        # Should not raise.
        invalidate_context("cand-1", "job-1", store=store)


class TestIsValidCachedContext:
    def test_valid_context_passes(self):
        context = AgentContext(
            candidate_id="cand-1",
            job_id="job-1",
            match_score=82.0,
            explanation={"overall_alignment_summary": "ok"},
        )
        assert _is_valid_cached_context(context, "cand-1", "job-1") is True

    def test_candidate_id_mismatch_fails(self):
        context = AgentContext(
            candidate_id="cand-2", job_id="job-1", match_score=82.0,
            explanation={"a": "b"},
        )
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False

    def test_job_id_mismatch_fails(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-2", match_score=82.0,
            explanation={"a": "b"},
        )
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False

    def test_missing_explanation_fails(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0, explanation={},
        )
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False

    def test_missing_match_score_fails(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            explanation={"a": "b"},
        )
        context.match_score = None
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False

    def test_missing_matched_skills_fails(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            explanation={"a": "b"},
        )
        context.matched_skills = None
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False

    def test_missing_missing_skills_fails(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            explanation={"a": "b"},
        )
        context.missing_skills = None
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False


# ---------------------------------------------------------------------------
# ContextStore abstraction
# ---------------------------------------------------------------------------


class TestContextStoreAbstraction:
    def test_context_store_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            ContextStore()  # type: ignore[abstract]

    def test_in_memory_context_store_implements_context_store(self):
        store = InMemoryContextStore()
        assert isinstance(store, ContextStore)

    def test_agent_context_store_alias_still_works(self):
        # Backward compatibility: AgentContextStore must still exist and
        # behave exactly like InMemoryContextStore.
        store = AgentContextStore()
        assert isinstance(store, ContextStore)
        assert isinstance(store, InMemoryContextStore)

    def test_save_load_exists_roundtrip(self):
        store = InMemoryContextStore()
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=90.0)

        assert store.exists("cand-1", "job-1") is False
        store.save(context)
        assert store.exists("cand-1", "job-1") is True
        assert store.load("cand-1", "job-1") is context

    def test_load_returns_none_for_missing_key(self):
        store = InMemoryContextStore()
        assert store.load("nope", "nope") is None

    def test_delete_removes_a_stored_context(self):
        store = InMemoryContextStore()
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=90.0)
        store.save(context)

        store.delete("cand-1", "job-1")

        assert store.exists("cand-1", "job-1") is False
        assert store.load("cand-1", "job-1") is None

    def test_delete_is_a_no_op_when_nothing_stored(self):
        store = InMemoryContextStore()
        # Should not raise even though nothing was ever saved for this pair.
        store.delete("nope", "nope")
        assert store.exists("nope", "nope") is False

    def test_get_set_aliases_still_work(self):
        # Backward-compatible get()/set() must behave identically to
        # load()/save().
        store = InMemoryContextStore()
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=90.0)

        store.set(context)
        assert store.get("cand-1", "job-1") is context

    def test_a_second_store_implementation_satisfies_the_interface(self):
        # Demonstrates the whole point of the abstraction: a future
        # RedisContextStore just needs to implement save/load/exists -
        # the agent never needs to change.
        class StubRedisContextStore(ContextStore):
            def __init__(self):
                self._data = {}

            def save(self, context):
                self._data[(context.candidate_id, context.job_id)] = context

            def load(self, candidate_id, job_id):
                return self._data.get((candidate_id, job_id))

            def exists(self, candidate_id, job_id):
                return (candidate_id, job_id) in self._data

            def delete(self, candidate_id, job_id):
                self._data.pop((candidate_id, job_id), None)

        stub_store = StubRedisContextStore()
        payload = '{"overall_alignment_summary": "via stub redis"}'

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=payload,
        ):
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=stub_store,
            )

        assert stub_store.exists("cand-1", "job-1") is True
        assert context.explanation["overall_alignment_summary"] == "via stub redis"


# ---------------------------------------------------------------------------
# load_context - pure lookup, no side effects
# ---------------------------------------------------------------------------


class TestLoadContext:
    def test_returns_none_when_not_found(self):
        store = AgentContextStore()
        assert load_context("cand-1", "job-1", store=store) is None

    def test_returns_stored_context(self):
        store = AgentContextStore()
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=90.0)
        store.set(context)

        assert load_context("cand-1", "job-1", store=store) is context


# ---------------------------------------------------------------------------
# answer_followup_question - reuses context, never re-runs analysis
# ---------------------------------------------------------------------------


class TestAnswerFollowupQuestion:
    def _sample_context(self) -> AgentContext:
        return AgentContext(
            candidate_id="cand-1",
            job_id="job-1",
            match_score=82.0,
            matched_skills=["Python", "Docker"],
            missing_skills=["REST APIs", "PostgreSQL"],
            explanation={"overall_alignment_summary": "Good fit overall."},
        )

    def test_happy_path_returns_gemini_answer(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="You're missing REST API experience specifically.",
        ) as mock_call:
            answer = answer_followup_question(
                self._sample_context(), "Why am I missing REST APIs?"
            )

        mock_call.assert_called_once()
        assert "REST API" in answer

    def test_falls_back_when_gemini_unavailable(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=None,
        ):
            answer = answer_followup_question(self._sample_context(), "Why?")

        assert answer  # non-empty fallback string
        assert "explanation" in answer.lower() or "match" in answer.lower()

    def test_falls_back_on_empty_response(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="   ",
        ):
            answer = answer_followup_question(self._sample_context(), "Why?")

        assert answer

    def test_prompt_includes_context_not_recomputed_data(self):
        # Confirm the prompt passed to Gemini is built purely from the
        # context object - no Skill Gap or matching call is made here.
        captured_prompt = {}

        def _capture(prompt, model=None, api_key=None, **kwargs):
            captured_prompt["value"] = prompt
            return "answer"

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            side_effect=_capture,
        ):
            answer_followup_question(self._sample_context(), "What about PostgreSQL?")

        assert "82.0" in captured_prompt["value"]
        assert "PostgreSQL" in captured_prompt["value"]
        assert "What about PostgreSQL?" in captured_prompt["value"]


# ---------------------------------------------------------------------------
# MatchExplanationAgent - dependency-injected ContextStore, no global state
# ---------------------------------------------------------------------------


class TestMatchExplanationAgentDependencyInjection:
    def test_requires_a_store_at_construction(self):
        with pytest.raises(TypeError):
            MatchExplanationAgent()  # type: ignore[call-arg]

    def test_uses_the_injected_store_not_the_global_default(self):
        store_a = InMemoryContextStore()
        store_b = InMemoryContextStore()
        agent_a = MatchExplanationAgent(store=store_a)

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "via agent_a"}',
        ):
            agent_a.get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(), _sample_match_result()
            )

        # Only store_a should have the context; store_b (and the global
        # default_store) must be untouched.
        assert store_a.exists("cand-1", "job-1") is True
        assert store_b.exists("cand-1", "job-1") is False

    def test_cache_hit_via_agent_does_not_call_gemini_again(self):
        store = InMemoryContextStore()
        agent = MatchExplanationAgent(store=store)

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "first"}',
        ) as mock_call:
            first = agent.get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(), _sample_match_result()
            )
            second = agent.get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert first is second
        mock_call.assert_called_once()

    def test_load_context_uses_injected_store(self):
        store = InMemoryContextStore()
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=90.0)
        store.save(context)

        agent = MatchExplanationAgent(store=store)
        assert agent.load_context("cand-1", "job-1") is context

    def test_invalidate_context_uses_injected_store(self):
        store = InMemoryContextStore()
        store.save(AgentContext(candidate_id="cand-1", job_id="job-1", match_score=90.0))

        agent = MatchExplanationAgent(store=store)
        agent.invalidate_context("cand-1", "job-1")

        assert store.exists("cand-1", "job-1") is False

    def test_answer_followup_question_via_agent(self):
        store = InMemoryContextStore()
        agent = MatchExplanationAgent(store=store)
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            explanation={"overall_alignment_summary": "ok"},
        )

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="Here's your answer.",
        ):
            answer = agent.answer_followup_question(context, "Why?")

        assert answer == "Here's your answer."


# ---------------------------------------------------------------------------
# context_version
# ---------------------------------------------------------------------------


class TestContextVersion:
    def test_new_context_defaults_to_current_version(self):
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=82.0)
        assert context.context_version == CURRENT_CONTEXT_VERSION

    def test_to_dict_includes_context_version(self):
        context = AgentContext(candidate_id="cand-1", job_id="job-1", match_score=82.0)
        assert context.to_dict()["context_version"] == CURRENT_CONTEXT_VERSION

    def test_from_dict_defaults_missing_version_to_1(self):
        # Simulates loading a record written before context_version existed.
        data = {
            "candidate_id": "cand-1",
            "job_id": "job-1",
            "match_score": 82.0,
            "matched_skills": ["Python"],
            "missing_skills": ["Docker"],
            "explanation": {"a": "b"},
        }
        context = AgentContext.from_dict(data)
        assert context.context_version == 1

    def test_from_dict_roundtrips_an_explicit_version(self):
        data = {
            "candidate_id": "cand-1",
            "job_id": "job-1",
            "match_score": 82.0,
            "context_version": 1,
        }
        context = AgentContext.from_dict(data)
        assert context.context_version == 1

    def test_valid_context_with_current_version_passes_validation(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            explanation={"a": "b"}, context_version=CURRENT_CONTEXT_VERSION,
        )
        assert _is_valid_cached_context(context, "cand-1", "job-1") is True

    def test_unsupported_context_version_fails_validation(self):
        context = AgentContext(
            candidate_id="cand-1", job_id="job-1", match_score=82.0,
            explanation={"a": "b"}, context_version=999,
        )
        assert _is_valid_cached_context(context, "cand-1", "job-1") is False

    def test_unsupported_version_is_treated_as_cache_miss_and_regenerated(self):
        store = InMemoryContextStore()
        store.save(
            AgentContext(
                candidate_id="cand-1", job_id="job-1", match_score=82.0,
                explanation={"overall_alignment_summary": "old schema"},
                context_version=999,
            )
        )

        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "regenerated"}',
        ) as mock_call:
            context = get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        mock_call.assert_called_once()
        assert context.explanation["overall_alignment_summary"] == "regenerated"
        assert context.context_version == CURRENT_CONTEXT_VERSION


# ---------------------------------------------------------------------------
# Fallback response schema strengthening
# ---------------------------------------------------------------------------


class TestFallbackResponseSchema:
    def test_fallback_after_exhausted_retries_is_a_full_match_explanation(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="still not json {{{",
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert isinstance(explanation, MatchExplanation)
        dumped = explanation.model_dump()
        assert set(dumped.keys()) == {
            "overall_alignment_summary",
            "strengths",
            "gaps_or_missing_requirements",
            "recommendations",
            "next_steps",
        }
        assert isinstance(dumped["overall_alignment_summary"], str)
        assert dumped["overall_alignment_summary"] != ""
        for list_field in (
            "strengths",
            "gaps_or_missing_requirements",
            "recommendations",
            "next_steps",
        ):
            assert isinstance(dumped[list_field], list)

    def test_fallback_is_never_a_plain_string(self):
        result = _fallback_explanation(_sample_match_result())
        assert isinstance(result, MatchExplanation)
        assert not isinstance(result, str)


# ---------------------------------------------------------------------------
# Structured logging (cache hit/miss/invalid, retry, fallback)
# ---------------------------------------------------------------------------


class TestLogging:
    def test_cache_hit_is_logged(self, caplog):
        store = InMemoryContextStore()
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "x"}',
        ):
            get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        with caplog.at_level("INFO", logger="backend.services.match_explanation_agent"):
            get_or_create_explanation(
                "cand-1", "job-1", _sample_profile(), _sample_job(),
                _sample_match_result(), store=store,
            )

        assert any("cache_hit" in record.message for record in caplog.records)

    def test_cache_miss_is_logged(self, caplog):
        store = InMemoryContextStore()
        with caplog.at_level("INFO", logger="backend.services.match_explanation_agent"):
            with patch(
                "backend.services.match_explanation_agent.call_gemini",
                return_value='{"overall_alignment_summary": "x"}',
            ):
                get_or_create_explanation(
                    "cand-1", "job-1", _sample_profile(), _sample_job(),
                    _sample_match_result(), store=store,
                )

        assert any("cache_miss" in record.message for record in caplog.records)

    def test_invalid_cache_is_logged(self, caplog):
        with caplog.at_level("WARNING", logger="backend.services.match_explanation_agent"):
            context = AgentContext(
                candidate_id="cand-1", job_id="job-1", match_score=82.0,
                explanation={}, context_version=CURRENT_CONTEXT_VERSION,
            )
            _is_valid_cached_context(context, "cand-1", "job-1")

        assert any("cache_invalid" in record.message for record in caplog.records)

    def test_gemini_retry_is_logged(self, caplog):
        with caplog.at_level("WARNING", logger="backend.services.match_explanation_agent"):
            with patch(
                "backend.services.match_explanation_agent.call_gemini",
                return_value="not json {{{",
            ):
                generate_match_explanation(
                    _sample_profile(), _sample_job(), _sample_match_result()
                )

        assert any("retry" in record.message for record in caplog.records)

    def test_fallback_usage_is_logged(self, caplog):
        with caplog.at_level("INFO", logger="backend.services.match_explanation_agent"):
            with patch(
                "backend.services.match_explanation_agent.call_gemini",
                return_value=None,
            ):
                generate_match_explanation(
                    _sample_profile(), _sample_job(), _sample_match_result()
                )

        assert any("fallback" in record.message for record in caplog.records)

    def test_logs_never_contain_skill_or_explanation_content(self, caplog):
        # Logging should only ever mention identifiers/counts, never the
        # candidate's actual skills or explanation text.
        store = InMemoryContextStore()
        with caplog.at_level("INFO", logger="backend.services.match_explanation_agent"):
            with patch(
                "backend.services.match_explanation_agent.call_gemini",
                return_value='{"overall_alignment_summary": "a very specific secret detail"}',
            ):
                get_or_create_explanation(
                    "cand-1", "job-1", _sample_profile(), _sample_job(),
                    _sample_match_result(), store=store,
                )

        for record in caplog.records:
            assert "a very specific secret detail" not in record.message
            assert "REST APIs" not in record.message
            assert "PostgreSQL" not in record.message

    def test_schema_validation_failure_does_not_leak_response_content(self, caplog):
        # A response that fails schema validation (wrong field type) still
        # gets logged (as a WARNING, with a count of errors) - but pydantic's
        # ValidationError string representation normally echoes back the
        # actual offending value. That value must never end up in the logs,
        # even when it looks like it could contain candidate-derived text.
        bad_payload = (
            '{"overall_alignment_summary": '
            '{"nested": "a very specific secret detail"}}'
        )
        with caplog.at_level("WARNING", logger="backend.services.match_explanation_agent"):
            with patch(
                "backend.services.match_explanation_agent.call_gemini",
                return_value=bad_payload,
            ):
                explanation = generate_match_explanation(
                    _sample_profile(), _sample_job(), _sample_match_result()
                )

        # Still degrades safely to the deterministic fallback...
        assert explanation == _fallback_explanation(_sample_match_result())
        # ...and the raw offending value never appears in any log record.
        for record in caplog.records:
            assert "a very specific secret detail" not in record.message
            assert "nested" not in record.message


# ---------------------------------------------------------------------------
# Deterministic Gemini configuration
# ---------------------------------------------------------------------------


class TestDeterministicGeminiConfig:
    def test_generate_match_explanation_requests_deterministic_json(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "x"}',
        ) as mock_call:
            generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert mock_call.call_count == 1
        _, kwargs = mock_call.call_args
        assert kwargs["temperature"] == 0.0
        assert kwargs["response_mime_type"] == "application/json"

    def test_retry_attempt_also_requests_deterministic_json(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="not json {{{",
        ) as mock_call:
            generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        # One initial attempt + one retry, both with the same determinism args.
        assert mock_call.call_count == 2
        for call in mock_call.call_args_list:
            assert call.kwargs["temperature"] == 0.0
            assert call.kwargs["response_mime_type"] == "application/json"

    def test_answer_followup_question_requests_temperature_but_not_json_mode(self):
        context = AgentContext(
            candidate_id="cand-1",
            job_id="job-1",
            match_score=82.0,
            matched_skills=["Python"],
            missing_skills=["Docker"],
            explanation={"overall_alignment_summary": "ok"},
        )
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value="Plain text answer.",
        ) as mock_call:
            answer_followup_question(context, "Why is my score not higher?")

        _, kwargs = mock_call.call_args
        assert kwargs["temperature"] == 0.0
        # The follow-up answer is intentionally plain text - it must never
        # force JSON output mode, which would fight the prompt's own
        # "respond in plain text" instruction.
        assert "response_mime_type" not in kwargs


# ---------------------------------------------------------------------------
# _is_explanation_consistent_with_score: pure tone-check unit tests
# ---------------------------------------------------------------------------


class TestIsExplanationConsistentWithScore:
    def test_high_score_with_neutral_summary_is_consistent(self):
        explanation = MatchExplanation(
            overall_alignment_summary="The candidate aligns well with most requirements."
        )
        assert _is_explanation_consistent_with_score(explanation, 90.0) is True

    def test_high_score_with_negative_phrase_is_inconsistent(self):
        explanation = MatchExplanation(
            overall_alignment_summary="Overall, this is a poor fit for the role."
        )
        assert _is_explanation_consistent_with_score(explanation, 90.0) is False

    def test_low_score_with_improvement_focused_summary_is_consistent(self):
        explanation = MatchExplanation(
            overall_alignment_summary=(
                "There are several gaps to address before this becomes a "
                "stronger match."
            )
        )
        assert _is_explanation_consistent_with_score(explanation, 20.0) is True

    def test_low_score_with_overclaiming_phrase_is_inconsistent(self):
        explanation = MatchExplanation(
            overall_alignment_summary="This candidate is an excellent fit for the role."
        )
        assert _is_explanation_consistent_with_score(explanation, 20.0) is False

    def test_medium_score_band_is_lenient_even_with_extreme_phrases(self):
        # The medium band deliberately applies no tone check at all, to
        # avoid false positives on legitimately balanced language.
        negative = MatchExplanation(overall_alignment_summary="This is a poor fit overall.")
        positive = MatchExplanation(overall_alignment_summary="This is an excellent fit.")
        assert _is_explanation_consistent_with_score(negative, 55.0) is True
        assert _is_explanation_consistent_with_score(positive, 55.0) is True

    def test_score_at_high_threshold_boundary_is_treated_as_high(self):
        explanation = MatchExplanation(overall_alignment_summary="This is a poor fit.")
        assert _is_explanation_consistent_with_score(explanation, 75.0) is False

    def test_score_at_low_threshold_boundary_is_treated_as_medium(self):
        explanation = MatchExplanation(overall_alignment_summary="This is an excellent fit.")
        assert _is_explanation_consistent_with_score(explanation, 40.0) is True

    def test_case_insensitive_phrase_matching(self):
        explanation = MatchExplanation(overall_alignment_summary="This is a POOR FIT overall.")
        assert _is_explanation_consistent_with_score(explanation, 90.0) is False


# ---------------------------------------------------------------------------
# Explanation consistency validation: integration with generate_match_explanation
# and get_or_create_explanation
# ---------------------------------------------------------------------------


class TestExplanationConsistencyValidation:
    def test_falls_back_when_tone_contradicts_a_high_score(self, caplog):
        # _sample_match_result() has match_score=82.0 (high bucket).
        with caplog.at_level("WARNING", logger="backend.services.match_explanation_agent"):
            with patch(
                "backend.services.match_explanation_agent.call_gemini",
                return_value='{"overall_alignment_summary": "This is a poor fit overall."}',
            ) as mock_call:
                explanation = generate_match_explanation(
                    _sample_profile(), _sample_job(), _sample_match_result()
                )

        assert explanation == _fallback_explanation(_sample_match_result())
        # A tone mismatch degrades straight to the fallback - it is not
        # treated as an invalid-JSON case and does not trigger a retry.
        assert mock_call.call_count == 1
        assert any("inconsistent_tone" in r.message for r in caplog.records)

    def test_falls_back_when_tone_contradicts_a_low_score(self):
        low_score_result = MatchResult(
            match_score=15.0,
            matched_skills=["Python"],
            missing_skills=["Docker", "Kubernetes", "AWS"],
        )
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "This candidate is an excellent fit."}',
        ) as mock_call:
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), low_score_result
            )

        assert explanation == _fallback_explanation(low_score_result)
        assert mock_call.call_count == 1

    def test_consistent_explanation_is_returned_unchanged(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=(
                '{"overall_alignment_summary": '
                '"The candidate matches most requirements well."}'
            ),
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )

        assert (
            explanation.overall_alignment_summary
            == "The candidate matches most requirements well."
        )

    def test_inconsistent_tone_never_gets_cached_by_get_or_create_explanation(self):
        # This is the "before saving into AgentContext" checkpoint: an
        # inconsistent response must never make it into the store, only
        # the deterministic fallback should.
        store = InMemoryContextStore()
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value=(
                '{"overall_alignment_summary": "This is a poor fit overall.", '
                '"strengths": ["Python"]}'
            ),
        ):
            context = get_or_create_explanation(
                "cand-1",
                "job-1",
                _sample_profile(),
                _sample_job(),
                _sample_match_result(),
                store=store,
            )

        assert (
            context.explanation
            == _fallback_explanation(_sample_match_result()).model_dump()
        )
        # And the same fallback is what actually landed in the store.
        stored = store.load("cand-1", "job-1")
        assert (
            stored.explanation
            == _fallback_explanation(_sample_match_result()).model_dump()
        )

    def test_does_not_recalculate_or_modify_the_score_on_a_tone_mismatch(self):
        with patch(
            "backend.services.match_explanation_agent.call_gemini",
            return_value='{"overall_alignment_summary": "This is a poor fit overall."}',
        ):
            explanation = generate_match_explanation(
                _sample_profile(), _sample_job(), _sample_match_result()
            )
            context = build_agent_context(
                "cand-1", "job-1", _sample_match_result(), explanation
            )

        # The score and skill lists are untouched - only the explanation
        # content changed (to the fallback).
        assert context.match_score == 82.0
        assert context.matched_skills == ["Python", "Docker"]
        assert context.missing_skills == ["REST APIs", "PostgreSQL"]
