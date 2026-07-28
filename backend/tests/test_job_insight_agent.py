"""Tests for the Job Insight Agent (Week 3 - Skill Gap task).

Covers:
- `MatchedJob` / `JobInsight` model serialization round-trips.
- `JobFitInsight` schema validation.
- Deterministic fallback when Gemini is unavailable or returns
  malformed/invalid JSON - built only from the match result, never
  invents data or changes the score.
- `generate_job_insight` happy path (mocked `call_gemini`), and the
  retry-once-on-invalid-JSON behavior.
- Deterministic Gemini config (`temperature=0.0`,
  `response_mime_type="application/json"`) is requested on every call.
- `generate_top_matches_insights`: preserves every existing job field,
  never touches `match_score`, keeps shortlist order, and one job's
  Gemini failure doesn't affect the others.
- `build_ui_summary` / `render_ui_summary_markdown` shape.
- `job_insight` route: HTTP contract via FastAPI TestClient.
- End-to-end usage of the existing service/endpoint contract via a
  sample `candidate_profile` + `top_jobs` JSON fixture
  (`fixtures/job_insight_sample_request.json`) - no matching engine or
  pipeline involved, just the Job Insight Agent's own contract.

These tests never call the real Gemini API - `call_gemini` is mocked
throughout.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.job import JobInfo
from backend.models.job_insight import JobFitInsight, JobInsight, MatchedJob
from backend.models.match_result import MatchResult
from backend.models.profile import Profile
from backend.routes.job_insight import TopMatchesInsightRequest
from backend.routes.job_insight import router as job_insight_router
from backend.services.job_insight_agent import (
    _fallback_insight,
    _is_complete_insight,
    _try_parse_insight,
    build_job_insight,
    build_ui_summary,
    generate_job_insight,
    generate_job_insights,
    generate_top_matches_insights,
    generate_top_matches_summary,
    render_ui_summary_markdown,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_sample_top_jobs_request() -> dict:
    """Load the sample candidate_profile + top_jobs request fixture.

    This fixture (`fixtures/job_insight_sample_request.json`) matches
    `backend.routes.job_insight.TopMatchesInsightRequest`'s schema
    exactly, so it's directly POST-able to `/job-insight/top-matches`
    with no transformation - see `TestSampleJsonFixtureEndToEnd`.
    """
    with open(FIXTURES_DIR / "job_insight_sample_request.json", encoding="utf-8") as f:
        return json.load(f)


def _sample_profile() -> Profile:
    return Profile(
        user_id="cand-1",
        skills=["Python", "FastAPI", "Docker"],
        target_role="Backend Developer",
        experience_level="junior",
    )


def _sample_matched_job(
    job_id: str = "job-1", match_score: float = 82.0
) -> MatchedJob:
    return MatchedJob(
        job=JobInfo(
            job_id=job_id,
            title="Backend Developer",
            company="Acme Corp",
            required_skills=["Python", "REST APIs", "Docker", "PostgreSQL"],
        ),
        match_result=MatchResult(
            match_score=match_score,
            matched_skills=["Python", "Docker"],
            missing_skills=["REST APIs", "PostgreSQL"],
        ),
    )


def _sample_top_3() -> list:
    return [
        _sample_matched_job("job-1", 88.0),
        _sample_matched_job("job-2", 65.0),
        _sample_matched_job("job-3", 40.0),
    ]


# ---------------------------------------------------------------------------
# MatchedJob / JobInsight model serialization
# ---------------------------------------------------------------------------


class TestMatchedJobModel:
    def test_to_dict_and_from_dict_round_trip(self):
        matched_job = _sample_matched_job()

        data = matched_job.to_dict()
        rebuilt = MatchedJob.from_dict(data)

        assert rebuilt.job.job_id == matched_job.job.job_id
        assert rebuilt.job.title == matched_job.job.title
        assert rebuilt.job.company == matched_job.job.company
        assert rebuilt.job.required_skills == matched_job.job.required_skills
        assert rebuilt.match_result.match_score == matched_job.match_result.match_score
        assert rebuilt.match_result.matched_skills == matched_job.match_result.matched_skills
        assert rebuilt.match_result.missing_skills == matched_job.match_result.missing_skills


class TestJobInsightModel:
    def test_to_dict_contains_all_preserved_and_appended_fields(self):
        insight = JobInsight(
            job_id="job-1",
            title="Backend Developer",
            company="Acme Corp",
            required_skills=["Python", "Docker"],
            match_score=82.0,
            matched_skills=["Python"],
            missing_skills=["Docker"],
            strength="Strong Python background.",
            weakness="No Docker experience listed.",
            recommendation="Consider learning Docker basics.",
        )

        data = insight.to_dict()

        assert data == {
            "job_id": "job-1",
            "title": "Backend Developer",
            "company": "Acme Corp",
            "required_skills": ["Python", "Docker"],
            "match_score": 82.0,
            "matched_skills": ["Python"],
            "missing_skills": ["Docker"],
            "strength": "Strong Python background.",
            "weakness": "No Docker experience listed.",
            "recommendation": "Consider learning Docker basics.",
        }


# ---------------------------------------------------------------------------
# JobFitInsight schema
# ---------------------------------------------------------------------------


class TestJobFitInsightSchema:
    def test_accepts_a_fully_populated_valid_response(self):
        insight = JobFitInsight.model_validate(
            {
                "strength": "Strong Python background.",
                "weakness": "No Docker experience listed.",
                "recommendation": "Consider learning Docker basics.",
            }
        )

        assert insight.strength == "Strong Python background."
        assert insight.weakness == "No Docker experience listed."
        assert insight.recommendation == "Consider learning Docker basics."

    def test_missing_fields_default_to_empty_strings(self):
        insight = JobFitInsight.model_validate({})

        assert insight.strength == ""
        assert insight.weakness == ""
        assert insight.recommendation == ""


class TestIsCompleteInsight:
    def test_fully_populated_insight_is_complete(self):
        insight = JobFitInsight(strength="a", weakness="b", recommendation="c")
        assert _is_complete_insight(insight) is True

    def test_missing_one_field_is_incomplete(self):
        # Simulates a Gemini response that omitted "weakness" - Pydantic's
        # default fills it with "", which still needs to be caught here.
        insight = JobFitInsight(strength="a", weakness="", recommendation="c")
        assert _is_complete_insight(insight) is False

    def test_whitespace_only_field_is_incomplete(self):
        insight = JobFitInsight(strength="a", weakness="   ", recommendation="c")
        assert _is_complete_insight(insight) is False

    def test_all_fields_missing_is_incomplete(self):
        insight = JobFitInsight()
        assert _is_complete_insight(insight) is False


# ---------------------------------------------------------------------------
# _try_parse_insight
# ---------------------------------------------------------------------------


class TestTryParseInsight:
    def test_parses_a_valid_response(self):
        insight = _try_parse_insight(
            '{"strength": "a", "weakness": "b", "recommendation": "c"}'
        )
        assert insight == JobFitInsight(strength="a", weakness="b", recommendation="c")

    def test_strips_markdown_code_fences(self):
        insight = _try_parse_insight(
            '```json\n{"strength": "a", "weakness": "b", "recommendation": "c"}\n```'
        )
        assert insight == JobFitInsight(strength="a", weakness="b", recommendation="c")

    def test_empty_response_returns_none(self):
        assert _try_parse_insight("") is None
        assert _try_parse_insight("   ") is None

    def test_invalid_json_returns_none(self):
        assert _try_parse_insight("not json {{{") is None

    def test_non_object_json_returns_none(self):
        assert _try_parse_insight("[1, 2, 3]") is None

    def test_response_missing_a_required_field_returns_none(self):
        # Schema-valid (missing field defaults to "") but incomplete -
        # must be rejected, not silently accepted with an empty field.
        result = _try_parse_insight('{"strength": "a", "recommendation": "c"}')
        assert result is None

    def test_response_with_an_empty_field_returns_none(self):
        result = _try_parse_insight(
            '{"strength": "a", "weakness": "", "recommendation": "c"}'
        )
        assert result is None

    def test_response_with_a_whitespace_only_field_returns_none(self):
        result = _try_parse_insight(
            '{"strength": "a", "weakness": "   ", "recommendation": "c"}'
        )
        assert result is None

    def test_incomplete_response_is_logged_without_leaking_content(self, caplog):
        with caplog.at_level("WARNING", logger="backend.services.job_insight_agent"):
            result = _try_parse_insight(
                '{"strength": "a very specific secret detail", "weakness": "", "recommendation": "c"}'
            )

        assert result is None
        for record in caplog.records:
            assert "a very specific secret detail" not in record.message

    def test_schema_violation_does_not_leak_response_content(self, caplog):
        # strength must be a string - passing a dict fails validation, and
        # the raw offending value must never appear in the logs.
        bad_payload = '{"strength": {"nested": "a very specific secret detail"}}'
        with caplog.at_level("WARNING", logger="backend.services.job_insight_agent"):
            result = _try_parse_insight(bad_payload)

        assert result is None
        for record in caplog.records:
            assert "a very specific secret detail" not in record.message
            assert "nested" not in record.message


# ---------------------------------------------------------------------------
# _fallback_insight
# ---------------------------------------------------------------------------


class TestFallbackInsight:
    def test_built_only_from_match_result_data(self):
        matched_job = _sample_matched_job()

        insight = _fallback_insight(matched_job)

        assert "Python" in insight.strength
        assert "Docker" in insight.strength
        assert "REST APIs" in insight.weakness
        assert "PostgreSQL" in insight.weakness
        assert "REST APIs" in insight.recommendation

    def test_no_matched_skills_produces_a_neutral_strength(self):
        matched_job = MatchedJob(
            job=JobInfo(job_id="job-x", title="Data Analyst"),
            match_result=MatchResult(match_score=10.0, matched_skills=[], missing_skills=["SQL"]),
        )

        insight = _fallback_insight(matched_job)

        assert insight.strength
        assert "SQL" in insight.weakness

    def test_no_missing_skills_produces_a_positive_recommendation(self):
        matched_job = MatchedJob(
            job=JobInfo(job_id="job-x", title="Data Analyst"),
            match_result=MatchResult(match_score=100.0, matched_skills=["SQL"], missing_skills=[]),
        )

        insight = _fallback_insight(matched_job)

        assert "applying" in insight.recommendation.lower()

    def test_never_invents_a_skill_not_in_match_result(self):
        matched_job = _sample_matched_job()

        insight = _fallback_insight(matched_job)

        for text in (insight.strength, insight.weakness, insight.recommendation):
            assert "Kubernetes" not in text
            assert "AWS" not in text


# ---------------------------------------------------------------------------
# generate_job_insight: happy path, retry, fallback, determinism config
# ---------------------------------------------------------------------------


class TestGenerateJobInsight:
    def test_falls_back_gracefully_when_prompt_building_fails(self):
        # Simulates an infra/config failure (e.g. a missing or unreadable
        # job_insight.md) rather than "the AI behaved badly" - must still
        # degrade to the deterministic fallback instead of raising, and
        # must never call Gemini at all since there's no prompt to send.
        matched_job = _sample_matched_job()
        with patch(
            "backend.services.job_insight_agent._build_insight_prompt",
            side_effect=OSError("prompt file not found"),
        ), patch(
            "backend.services.job_insight_agent.call_gemini"
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), matched_job)

        assert insight == _fallback_insight(matched_job)
        mock_call.assert_not_called()

    def test_happy_path_returns_validated_insight(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value=(
                '{"strength": "Strong Python background.", '
                '"weakness": "No Docker experience listed.", '
                '"recommendation": "Consider learning Docker basics."}'
            ),
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), _sample_matched_job())

        assert insight.strength == "Strong Python background."
        assert insight.weakness == "No Docker experience listed."
        assert insight.recommendation == "Consider learning Docker basics."
        assert mock_call.call_count == 1

    def test_requests_deterministic_json_output(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ) as mock_call:
            generate_job_insight(_sample_profile(), _sample_matched_job())

        _, kwargs = mock_call.call_args
        assert kwargs["temperature"] == 0.0
        assert kwargs["response_mime_type"] == "application/json"

    def test_retries_once_on_invalid_json_then_succeeds(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            side_effect=[
                "not json {{{",
                '{"strength": "a", "weakness": "b", "recommendation": "c"}',
            ],
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), _sample_matched_job())

        assert insight == JobFitInsight(strength="a", weakness="b", recommendation="c")
        assert mock_call.call_count == 2

    def test_falls_back_after_two_invalid_json_responses(self):
        matched_job = _sample_matched_job()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value="not json {{{",
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), matched_job)

        assert insight == _fallback_insight(matched_job)
        assert mock_call.call_count == 2

    def test_retries_once_on_incomplete_json_then_succeeds(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            side_effect=[
                # Missing "recommendation" - schema-valid but incomplete.
                '{"strength": "a", "weakness": "b"}',
                '{"strength": "a", "weakness": "b", "recommendation": "c"}',
            ],
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), _sample_matched_job())

        assert insight == JobFitInsight(strength="a", weakness="b", recommendation="c")
        assert mock_call.call_count == 2

    def test_falls_back_after_two_incomplete_responses(self):
        # Every attempt is missing "weakness" - never saved, always retried
        # once, then degraded to the deterministic fallback.
        matched_job = _sample_matched_job()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "", "recommendation": "c"}',
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), matched_job)

        assert insight == _fallback_insight(matched_job)
        assert mock_call.call_count == 2

    def test_falls_back_when_gemini_unavailable(self):
        matched_job = _sample_matched_job()
        with patch(
            "backend.services.job_insight_agent.call_gemini", return_value=None
        ) as mock_call:
            insight = generate_job_insight(_sample_profile(), matched_job)

        assert insight == _fallback_insight(matched_job)
        assert mock_call.call_count == 1  # no retry for an unavailable/unconfigured Gemini

    def test_never_recalculates_the_score(self):
        matched_job = _sample_matched_job(match_score=82.0)
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            generate_job_insight(_sample_profile(), matched_job)

        # The input match_result is never mutated by generation.
        assert matched_job.match_result.match_score == 82.0


# ---------------------------------------------------------------------------
# build_job_insight: field preservation
# ---------------------------------------------------------------------------


class TestBuildJobInsight:
    def test_preserves_all_existing_job_fields_and_appends_the_three_new_ones(self):
        matched_job = _sample_matched_job()
        fit = JobFitInsight(strength="s", weakness="w", recommendation="r")

        insight = build_job_insight(matched_job, fit)

        assert insight.job_id == matched_job.job.job_id
        assert insight.title == matched_job.job.title
        assert insight.company == matched_job.job.company
        assert insight.required_skills == matched_job.job.required_skills
        assert insight.match_score == matched_job.match_result.match_score
        assert insight.matched_skills == matched_job.match_result.matched_skills
        assert insight.missing_skills == matched_job.match_result.missing_skills
        assert insight.strength == "s"
        assert insight.weakness == "w"
        assert insight.recommendation == "r"


# ---------------------------------------------------------------------------
# generate_top_matches_insights: batch behavior over the Top-3 shortlist
# ---------------------------------------------------------------------------


class TestGenerateTopMatchesInsights:
    def test_returns_one_insight_per_job_in_shortlist_order(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            insights = generate_top_matches_insights(_sample_profile(), _sample_top_3())

        assert [i.job_id for i in insights] == ["job-1", "job-2", "job-3"]

    def test_calls_gemini_once_per_job(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ) as mock_call:
            generate_top_matches_insights(_sample_profile(), _sample_top_3())

        assert mock_call.call_count == 3

    def test_does_not_modify_any_jobs_match_score(self):
        top_3 = _sample_top_3()
        original_scores = [job.match_result.match_score for job in top_3]

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            insights = generate_top_matches_insights(_sample_profile(), top_3)

        assert [i.match_score for i in insights] == original_scores

    def test_one_jobs_gemini_failure_does_not_affect_the_others(self):
        top_3 = _sample_top_3()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            side_effect=[
                '{"strength": "a", "weakness": "b", "recommendation": "c"}',  # job-1: fine
                None,  # job-2: Gemini unavailable -> fallback
                '{"strength": "x", "weakness": "y", "recommendation": "z"}',  # job-3: fine
            ],
        ):
            insights = generate_top_matches_insights(_sample_profile(), top_3)

        assert insights[0].strength == "a"
        assert insights[1] == build_job_insight(top_3[1], _fallback_insight(top_3[1]))
        assert insights[2].strength == "x"

    def test_empty_shortlist_returns_an_empty_list(self):
        with patch("backend.services.job_insight_agent.call_gemini") as mock_call:
            insights = generate_top_matches_insights(_sample_profile(), [])

        assert insights == []
        mock_call.assert_not_called()


# ---------------------------------------------------------------------------
# generate_job_insights: the requested batch entry point returning both the
# augmented jobs list and the UI-ready summary in one call
# ---------------------------------------------------------------------------


class TestGenerateJobInsights:
    def test_successful_generation_for_all_three_jobs(self):
        top_3 = _sample_top_3()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ) as mock_call:
            augmented_jobs, summary = generate_job_insights(_sample_profile(), top_3)

        assert mock_call.call_count == 3
        assert [job.job_id for job in augmented_jobs] == ["job-1", "job-2", "job-3"]
        assert all(job.strength == "a" for job in augmented_jobs)
        assert summary["job_count"] == 3

    def test_returns_the_same_augmented_jobs_as_generate_top_matches_insights(self):
        top_3 = _sample_top_3()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            expected_jobs = generate_top_matches_insights(_sample_profile(), top_3)

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            augmented_jobs, _ = generate_job_insights(_sample_profile(), top_3)

        assert augmented_jobs == expected_jobs

    def test_returns_the_same_summary_as_build_ui_summary(self):
        top_3 = _sample_top_3()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            augmented_jobs, summary = generate_job_insights(_sample_profile(), top_3)

        assert summary == build_ui_summary(augmented_jobs)

    def test_preserves_match_score_and_existing_job_fields_for_all_jobs(self):
        top_3 = _sample_top_3()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            augmented_jobs, _ = generate_job_insights(_sample_profile(), top_3)

        for original, augmented in zip(top_3, augmented_jobs):
            assert augmented.match_score == original.match_result.match_score
            assert augmented.matched_skills == original.match_result.matched_skills
            assert augmented.missing_skills == original.match_result.missing_skills
            assert augmented.required_skills == original.job.required_skills

    def test_fallback_behavior_for_an_incomplete_response_on_one_job(self):
        top_3 = _sample_top_3()
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            side_effect=[
                '{"strength": "a", "weakness": "b", "recommendation": "c"}',  # job-1: fine
                # job-2: incomplete (missing "recommendation"), twice in a
                # row -> retried once, then degraded to the fallback.
                '{"strength": "x", "weakness": "y"}',
                '{"strength": "x", "weakness": "y"}',
                '{"strength": "p", "weakness": "q", "recommendation": "r"}',  # job-3: fine
            ],
        ):
            augmented_jobs, summary = generate_job_insights(_sample_profile(), top_3)

        job2_fallback = _fallback_insight(top_3[1])
        assert augmented_jobs[1].strength == job2_fallback.strength
        assert augmented_jobs[1].weakness == job2_fallback.weakness
        assert augmented_jobs[1].recommendation == job2_fallback.recommendation
        # The fallback still shows up correctly in the UI summary too.
        contents = {s["label"]: s["content"] for s in summary["jobs"][1]["sections"]}
        assert contents["Recommendation"] == job2_fallback.recommendation

    def test_empty_shortlist_returns_empty_list_and_zero_job_summary(self):
        augmented_jobs, summary = generate_job_insights(_sample_profile(), [])

        assert augmented_jobs == []
        assert summary == {"job_count": 0, "jobs": []}


# ---------------------------------------------------------------------------
# UI-ready summary
# ---------------------------------------------------------------------------


class TestBuildUiSummary:
    def test_produces_labeled_sections_per_job(self):
        insight = JobInsight(
            job_id="job-1",
            title="Backend Developer",
            company="Acme Corp",
            match_score=82.0,
            matched_skills=["Python"],
            missing_skills=["Docker"],
            strength="Strong Python background.",
            weakness="No Docker experience listed.",
            recommendation="Consider learning Docker basics.",
        )

        summary = build_ui_summary([insight])

        assert summary["job_count"] == 1
        job_summary = summary["jobs"][0]
        assert job_summary["job_id"] == "job-1"
        assert job_summary["match_score"] == 82.0
        labels = [section["label"] for section in job_summary["sections"]]
        assert labels == ["Strength", "Weakness", "Recommendation"]
        contents = {s["label"]: s["content"] for s in job_summary["sections"]}
        assert contents["Strength"] == "Strong Python background."
        assert contents["Weakness"] == "No Docker experience listed."
        assert contents["Recommendation"] == "Consider learning Docker basics."

    def test_empty_list_produces_zero_job_count(self):
        summary = build_ui_summary([])
        assert summary == {"job_count": 0, "jobs": []}

    def test_preserves_shortlist_order(self):
        insights = [
            JobInsight(job_id="job-1", title="A", match_score=90.0),
            JobInsight(job_id="job-2", title="B", match_score=50.0),
        ]

        summary = build_ui_summary(insights)

        assert [j["job_id"] for j in summary["jobs"]] == ["job-1", "job-2"]


class TestRenderUiSummaryMarkdown:
    def test_renders_one_block_per_job_with_all_three_sections(self):
        insight = JobInsight(
            job_id="job-1",
            title="Backend Developer",
            company="Acme Corp",
            match_score=82.0,
            strength="Strong Python background.",
            weakness="No Docker experience listed.",
            recommendation="Consider learning Docker basics.",
        )

        markdown = render_ui_summary_markdown([insight])

        assert "Backend Developer" in markdown
        assert "Acme Corp" in markdown
        assert "82.0" in markdown
        assert "**Strength:** Strong Python background." in markdown
        assert "**Weakness:** No Docker experience listed." in markdown
        assert "**Recommendation:** Consider learning Docker basics." in markdown

    def test_empty_list_returns_a_friendly_message(self):
        assert render_ui_summary_markdown([]) == "No matched jobs to summarize."


class TestGenerateTopMatchesSummary:
    def test_is_equivalent_to_generate_then_build_summary(self):
        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            direct_insights = generate_top_matches_insights(_sample_profile(), _sample_top_3())
            expected = build_ui_summary(direct_insights)

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            actual = generate_top_matches_summary(_sample_profile(), _sample_top_3())

        assert actual == expected


# ---------------------------------------------------------------------------
# job_insight route
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(job_insight_router)
    return TestClient(app)


class TestJobInsightRoute:
    def test_top_matches_returns_200_with_enriched_jobs_and_ui_summary(
        self, client: TestClient
    ):
        payload = {
            "user_id": "u123",
            "target_role": "Backend Developer",
            "skills": ["Python", "FastAPI", "Docker"],
            "matched_jobs": [
                {
                    "job_id": "job-1",
                    "title": "Backend Developer",
                    "company": "Acme Corp",
                    "required_skills": ["Python", "REST APIs", "Docker", "PostgreSQL"],
                    "match_score": 82,
                    "matched_skills": ["Python", "Docker"],
                    "missing_skills": ["REST APIs", "PostgreSQL"],
                }
            ],
        }

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value=(
                '{"strength": "Strong Python background.", '
                '"weakness": "No REST API experience listed.", '
                '"recommendation": "Build a small REST API project."}'
            ),
        ):
            response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        body = response.json()

        # The augmented jobs list: existing fields preserved, three new ones appended.
        assert len(body["jobs"]) == 1
        job = body["jobs"][0]
        assert job["job_id"] == "job-1"
        assert job["title"] == "Backend Developer"
        assert job["company"] == "Acme Corp"
        assert job["required_skills"] == ["Python", "REST APIs", "Docker", "PostgreSQL"]
        assert job["match_score"] == 82
        assert job["matched_skills"] == ["Python", "Docker"]
        assert job["missing_skills"] == ["REST APIs", "PostgreSQL"]
        assert job["strength"] == "Strong Python background."
        assert job["weakness"] == "No REST API experience listed."
        assert job["recommendation"] == "Build a small REST API project."

        # The UI-ready summary: same job, formatted as labeled sections.
        assert body["ui_summary"]["job_count"] == 1
        job_summary = body["ui_summary"]["jobs"][0]
        assert job_summary["job_id"] == "job-1"
        assert job_summary["match_score"] == 82
        labels = [s["label"] for s in job_summary["sections"]]
        assert labels == ["Strength", "Weakness", "Recommendation"]

    def test_top_matches_without_gemini_configured_still_returns_200(
        self, client: TestClient, monkeypatch
    ):
        # No GEMINI_API_KEY set -> call_gemini degrades to None ->
        # deterministic fallback insight -> route still returns 200.
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        payload = {
            "user_id": "u999",
            "skills": ["Python"],
            "matched_jobs": [
                {
                    "job_id": "job-1",
                    "title": "Backend Developer",
                    "match_score": 50,
                    "matched_skills": ["Python"],
                    "missing_skills": ["Docker"],
                }
            ],
        }

        response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert "Docker" in body["jobs"][0]["weakness"]
        contents = {s["label"]: s["content"] for s in body["ui_summary"]["jobs"][0]["sections"]}
        assert "Docker" in contents["Weakness"]

    def test_top_matches_preserves_match_score_from_request(self, client: TestClient):
        payload = {
            "user_id": "u123",
            "skills": ["Python"],
            "matched_jobs": [
                {"job_id": "job-1", "title": "Role A", "match_score": 91.5},
                {"job_id": "job-2", "title": "Role B", "match_score": 33.0},
            ],
        }

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
        ):
            response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["jobs"][0]["match_score"] == 91.5
        assert body["jobs"][1]["match_score"] == 33.0
        assert body["ui_summary"]["jobs"][0]["match_score"] == 91.5
        assert body["ui_summary"]["jobs"][1]["match_score"] == 33.0

    def test_top_matches_calls_the_batch_service_method_once(self, client: TestClient):
        # The route must delegate the whole shortlist to
        # generate_job_insights in a single call - not call
        # generate_job_insight per job itself.
        payload = {
            "user_id": "u123",
            "skills": ["Python"],
            "matched_jobs": [
                {"job_id": "job-1", "title": "Role A", "match_score": 91.5},
                {"job_id": "job-2", "title": "Role B", "match_score": 33.0},
                {"job_id": "job-3", "title": "Role C", "match_score": 10.0},
            ],
        }

        with patch(
            "backend.routes.job_insight.generate_job_insights",
            wraps=generate_job_insights,
        ) as mock_service_call:
            with patch(
                "backend.services.job_insight_agent.call_gemini",
                return_value='{"strength": "a", "weakness": "b", "recommendation": "c"}',
            ):
                response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        mock_service_call.assert_called_once()

    def test_top_matches_with_empty_shortlist_returns_zero_jobs(self, client: TestClient):
        payload = {"user_id": "u123", "skills": ["Python"], "matched_jobs": []}

        response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        assert response.json() == {
            "jobs": [],
            "ui_summary": {"job_count": 0, "jobs": []},
        }


# ---------------------------------------------------------------------------
# End-to-end usage via a sample candidate_profile + top_jobs JSON fixture
#
# Demonstrates the Job Insight Agent is fully usable through its existing
# contract - both the service function and the HTTP endpoint - using a
# realistic sample payload. No matching engine, no pipeline: this is
# exactly the (candidate_profile, top_jobs) -> enriched jobs contract the
# agent already exposes.
# ---------------------------------------------------------------------------


class TestSampleJsonFixtureEndToEnd:
    def test_sample_payload_matches_the_endpoint_request_schema(self):
        # Confirms the fixture is a valid, directly POST-able example of
        # the route's request contract - not just a loose/illustrative
        # sample that happens to look similar.
        payload = _load_sample_top_jobs_request()

        request = TopMatchesInsightRequest.model_validate(payload)

        assert request.user_id == "cand-2001"
        assert len(request.matched_jobs) == 3

    def test_service_layer_consumes_the_sample_payload_directly(self):
        # Exercises generate_job_insights(candidate_profile, top_jobs)
        # directly - the function-level contract - using the sample
        # fixture's data, translated into the existing models.
        payload = _load_sample_top_jobs_request()

        profile = Profile(
            user_id=payload["user_id"],
            skills=payload["skills"],
            target_role=payload.get("target_role"),
            experience_level=payload.get("experience_level"),
        )
        top_jobs = [
            MatchedJob(
                job=JobInfo(
                    job_id=item["job_id"],
                    title=item["title"],
                    company=item.get("company"),
                    required_skills=item.get("required_skills", []),
                ),
                match_result=MatchResult(
                    match_score=item["match_score"],
                    matched_skills=item.get("matched_skills", []),
                    missing_skills=item.get("missing_skills", []),
                ),
            )
            for item in payload["matched_jobs"]
        ]

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value=(
                '{"strength": "Relevant skills for this role.", '
                '"weakness": "A gap worth addressing.", '
                '"recommendation": "A concrete next step."}'
            ),
        ):
            augmented_jobs, ui_summary = generate_job_insights(profile, top_jobs)

        assert len(augmented_jobs) == 3
        for original, augmented in zip(payload["matched_jobs"], augmented_jobs):
            # Every existing field preserved, unchanged.
            assert augmented.job_id == original["job_id"]
            assert augmented.title == original["title"]
            assert augmented.company == original.get("company")
            assert augmented.required_skills == original.get("required_skills", [])
            assert augmented.match_score == original["match_score"]
            assert augmented.matched_skills == original.get("matched_skills", [])
            assert augmented.missing_skills == original.get("missing_skills", [])
            # The three new fields appended.
            assert augmented.strength == "Relevant skills for this role."
            assert augmented.weakness == "A gap worth addressing."
            assert augmented.recommendation == "A concrete next step."

        assert ui_summary["job_count"] == 3

    def test_endpoint_consumes_the_sample_payload_directly(self, client: TestClient):
        # Exercises POST /job-insight/top-matches - the endpoint-level
        # contract - by posting the sample fixture as-is.
        payload = _load_sample_top_jobs_request()

        with patch(
            "backend.services.job_insight_agent.call_gemini",
            return_value=(
                '{"strength": "Relevant skills for this role.", '
                '"weakness": "A gap worth addressing.", '
                '"recommendation": "A concrete next step."}'
            ),
        ):
            response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        body = response.json()

        assert len(body["jobs"]) == 3
        for original, augmented in zip(payload["matched_jobs"], body["jobs"]):
            assert augmented["job_id"] == original["job_id"]
            assert augmented["title"] == original["title"]
            assert augmented["company"] == original.get("company")
            assert augmented["required_skills"] == original.get("required_skills", [])
            assert augmented["match_score"] == original["match_score"]
            assert augmented["matched_skills"] == original.get("matched_skills", [])
            assert augmented["missing_skills"] == original.get("missing_skills", [])
            assert augmented["strength"] == "Relevant skills for this role."
            assert augmented["weakness"] == "A gap worth addressing."
            assert augmented["recommendation"] == "A concrete next step."

        # Ready for Omar's UI: labeled sections for every job.
        assert body["ui_summary"]["job_count"] == 3
        for job_summary in body["ui_summary"]["jobs"]:
            labels = [section["label"] for section in job_summary["sections"]]
            assert labels == ["Strength", "Weakness", "Recommendation"]

    def test_endpoint_falls_back_gracefully_with_no_gemini_configured(
        self, client: TestClient, monkeypatch
    ):
        # Even with zero Gemini configuration, the sample payload still
        # produces a fully enriched, UI-ready response - via the
        # deterministic fallback, never an error.
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        payload = _load_sample_top_jobs_request()

        response = client.post("/job-insight/top-matches", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert len(body["jobs"]) == 3
        for job in body["jobs"]:
            assert job["strength"]
            assert job["weakness"]
            assert job["recommendation"]
