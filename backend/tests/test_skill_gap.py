"""Tests for the Skill-Gap lane (Sprint 1).

Covers:
- skill_taxonomy: normalization/aliasing correctness.
- skill_gap service: naive baseline gap analysis (both modes).
- skill_gap route: HTTP contract via FastAPI TestClient.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.profile import Profile
from backend.services import skill_taxonomy
from backend.services.gemini_matcher import SemanticMatcher, SemanticMatchResult, empty_result
from backend.services.skill_gap import (
    _DEFAULT_SEMANTIC_MATCH_THRESHOLD,
    _resolve_semantic_match_threshold,
    analyze_skill_gap,
)
from backend.routes.skill_gap import router as skill_gap_router


# ---------------------------------------------------------------------------
# skill_taxonomy
# ---------------------------------------------------------------------------

class TestNormalizeSkill:
    @pytest.mark.parametrize(
        "raw, expected_canonical",
        [
            ("JS", "JavaScript"),
            ("js", "JavaScript"),
            ("javascript", "JavaScript"),
            ("  JavaScript  ", "JavaScript"),
            ("Node", "Node.js"),
            ("nodejs", "Node.js"),
            ("node.js", "Node.js"),
            ("Postgres", "PostgreSQL"),
            ("postgresql", "PostgreSQL"),
            ("ML", "Machine Learning"),
            ("machine learning", "Machine Learning"),
            ("C#", "C#"),
            ("csharp", "C#"),
            ("REST API", "REST APIs"),
            ("rest apis", "REST APIs"),
        ],
    )
    def test_known_aliases_resolve_to_canonical(self, raw, expected_canonical):
        result = skill_taxonomy.normalize_skill(raw)
        assert result.canonical == expected_canonical
        assert result.known is True

    def test_unknown_skill_passes_through_unflagged(self):
        result = skill_taxonomy.normalize_skill("Quantum Basket Weaving")
        assert result.canonical == "Quantum Basket Weaving"
        assert result.known is False
        assert result.category is None

    def test_empty_string_yields_empty_canonical(self):
        result = skill_taxonomy.normalize_skill("   ")
        assert result.canonical == ""
        assert result.known is False

    def test_category_is_attached_for_known_skills(self):
        result = skill_taxonomy.normalize_skill("js")
        assert result.category == "language"

        result = skill_taxonomy.normalize_skill("react")
        assert result.category == "framework"

        result = skill_taxonomy.normalize_skill("postgres")
        assert result.category == "database"


class TestIsValidSkill:
    @pytest.mark.parametrize(
        "raw",
        [
            "Unknown Skill",
            "unknown skill",
            "  Unknown Skill  ",
            "Unknown",
            "UNKNOWN",
            "",
            "   ",
            None,
            "N/A",
            "none",
            "TBD",
        ],
    )
    def test_rejects_placeholder_and_empty_values(self, raw):
        assert skill_taxonomy.is_valid_skill(raw) is False

    @pytest.mark.parametrize("raw", ["Python", "JS", "SQL", "Unknown Language"])
    def test_accepts_real_or_unrecognized_skill_strings(self, raw):
        # "Unknown Language" is deliberately NOT in the placeholder set -
        # only exact sentinel values are rejected, not every string that
        # merely contains the word "unknown".
        assert skill_taxonomy.is_valid_skill(raw) is True


class TestNormalizeSkillPlaceholders:
    @pytest.mark.parametrize(
        "raw",
        ["Unknown Skill", "unknown skill", "Unknown", "", "   ", None],
    )
    def test_normalize_skill_yields_empty_canonical_for_placeholders(self, raw):
        result = skill_taxonomy.normalize_skill(raw)
        assert result.canonical == ""

    def test_normalize_skills_drops_placeholders_from_output(self):
        result = skill_taxonomy.canonical_skill_set(
            ["Python", "Unknown Skill", "SQL", "unknown", None, "  "]
        )
        assert result == ["Python", "SQL"]
        assert "Unknown Skill" not in result
        assert "Unknown" not in result


class TestNormalizeSkills:
    def test_deduplicates_equivalent_aliases(self):
        result = skill_taxonomy.normalize_skills(["JS", "JavaScript", "js"])
        assert len(result) == 1
        assert result[0].canonical == "JavaScript"

    def test_preserves_first_seen_order(self):
        result = skill_taxonomy.canonical_skill_set(["Python", "SQL", "React", "sql"])
        assert result == ["Python", "SQL", "React"]

    def test_mixes_known_and_unknown_skills(self):
        result = skill_taxonomy.canonical_skill_set(["Python", "Blockchain Wizardry"])
        assert "Python" in result
        assert "Blockchain Wizardry" in result

    def test_ignores_blank_entries(self):
        result = skill_taxonomy.canonical_skill_set(["Python", "", "   "])
        assert result == ["Python"]


# ---------------------------------------------------------------------------
# skill_gap service
# ---------------------------------------------------------------------------

class TestAnalyzeSkillGapWithJobPostings:
    def test_identifies_missing_skills_ranked_by_frequency(self):
        profile = Profile(
            user_id="u1",
            skills=["Python", "excel"],
            target_role="Data Analyst",
        )
        job_postings_skills = [
            ["Python", "SQL", "Power BI"],
            ["SQL", "Excel", "Tableau"],
            ["SQL", "Python"],
        ]

        gap = analyze_skill_gap(profile, job_postings_skills=job_postings_skills)

        assert gap.user_id == "u1"
        assert gap.target_role == "Data Analyst"
        assert "Python" in gap.matched_skills
        assert "Excel" in gap.matched_skills

        gap_skills = [g.skill for g in gap.gaps]
        # SQL appears in all 3 postings -> must be the top-priority gap.
        assert gap_skills[0] == "SQL"
        assert gap.gaps[0].priority == 1
        assert "SQL" in gap_skills
        assert "Power BI" in gap_skills
        assert "Tableau" in gap_skills
        # Priorities are strictly increasing and start at 1.
        priorities = [g.priority for g in gap.gaps]
        assert priorities == list(range(1, len(priorities) + 1))

    def test_gap_reason_mentions_skill_and_role(self):
        profile = Profile(user_id="u1", skills=[], target_role="Backend Engineer")
        job_postings_skills = [["Python"], ["Python"]]

        gap = analyze_skill_gap(profile, job_postings_skills=job_postings_skills)

        assert len(gap.gaps) == 1
        assert "Python" in gap.gaps[0].reason
        assert "Backend Engineer" in gap.gaps[0].reason

    def test_no_gaps_when_profile_covers_all_required_skills(self):
        profile = Profile(user_id="u1", skills=["Python", "SQL"], target_role="Analyst")
        job_postings_skills = [["Python", "SQL"], ["sql", "python"]]

        gap = analyze_skill_gap(profile, job_postings_skills=job_postings_skills)

        assert gap.gaps == []
        assert sorted(gap.matched_skills) == ["Python", "SQL"]

    def test_placeholder_skills_are_ignored_completely(self):
        # Some postings have no real requirements and use sentinel
        # values instead - these must never surface as required skills,
        # never be frequency-counted, and never appear as gaps.
        profile = Profile(user_id="u1", skills=["Python"], target_role="Data Analyst")
        job_postings_skills = [
            ["Python", "SQL"],
            ["Unknown Skill"],
            ["Unknown"],
            [],
            ["SQL", ""],
            ["SQL", None],
        ]

        gap = analyze_skill_gap(profile, job_postings_skills=job_postings_skills)

        assert "Unknown Skill" not in gap.required_skills
        assert "Unknown" not in gap.required_skills
        assert "" not in gap.required_skills

        gap_skills = [g.skill for g in gap.gaps]
        assert "Unknown Skill" not in gap_skills
        assert "Unknown" not in gap_skills
        # SQL appeared in 3 real postings and is still correctly the
        # only real gap (Python is already held).
        assert gap_skills == ["SQL"]
        assert all("Unknown" not in g.reason for g in gap.gaps)

    def test_aliases_in_profile_and_postings_are_reconciled(self):
        # Profile lists "JS", posting lists "JavaScript" - must match, not gap.
        profile = Profile(user_id="u1", skills=["JS"], target_role="Frontend Dev")
        job_postings_skills = [["JavaScript", "React"]]

        gap = analyze_skill_gap(profile, job_postings_skills=job_postings_skills)

        assert "JavaScript" in gap.matched_skills
        gap_skills = [g.skill for g in gap.gaps]
        assert gap_skills == ["React"]


class TestAnalyzeSkillGapWithOverride:
    def test_required_skills_override_ranks_by_input_order(self):
        profile = Profile(user_id="u2", skills=["Python"], target_role="Data Engineer")

        gap = analyze_skill_gap(
            profile,
            required_skills_override=["Python", "SQL", "Airflow"],
        )

        gap_skills = [g.skill for g in gap.gaps]
        assert gap_skills == ["SQL", "Airflow"]
        assert gap.gaps[0].priority == 1
        assert gap.gaps[1].priority == 2

    def test_override_takes_precedence_over_job_postings(self):
        profile = Profile(user_id="u2", skills=[], target_role="Analyst")

        gap = analyze_skill_gap(
            profile,
            job_postings_skills=[["Python", "SQL"]],
            required_skills_override=["Excel"],
        )

        assert gap.required_skills == ["Excel"]
        assert [g.skill for g in gap.gaps] == ["Excel"]


class TestAnalyzeSkillGapErrors:
    def test_raises_when_no_requirement_source_given(self):
        profile = Profile(user_id="u3", skills=["Python"], target_role="Analyst")

        with pytest.raises(ValueError):
            analyze_skill_gap(profile)


# ---------------------------------------------------------------------------
# SEMANTIC_MATCH_THRESHOLD config resolution
#
# The module-level SEMANTIC_MATCH_CONFIDENCE_THRESHOLD constant is fixed at
# import time, so these tests exercise the resolver function directly
# (with monkeypatched env vars) rather than reloading the module.
# ---------------------------------------------------------------------------


class TestSemanticMatchThresholdConfig:
    def test_default_value_is_0_75(self):
        assert _DEFAULT_SEMANTIC_MATCH_THRESHOLD == 0.75

    def test_falls_back_to_default_when_env_var_unset(self, monkeypatch):
        monkeypatch.delenv("SEMANTIC_MATCH_THRESHOLD", raising=False)
        assert _resolve_semantic_match_threshold() == 0.75

    def test_uses_valid_custom_value_from_env(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "0.6")
        assert _resolve_semantic_match_threshold() == 0.6

    def test_accepts_boundary_values_0_and_1(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "0.0")
        assert _resolve_semantic_match_threshold() == 0.0

        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "1.0")
        assert _resolve_semantic_match_threshold() == 1.0

    def test_falls_back_to_default_when_env_var_not_a_number(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "not-a-number")
        assert _resolve_semantic_match_threshold() == 0.75

    def test_falls_back_to_default_when_env_var_out_of_range(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "1.5")
        assert _resolve_semantic_match_threshold() == 0.75

        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "-0.1")
        assert _resolve_semantic_match_threshold() == 0.75

    def test_falls_back_to_default_when_env_var_is_empty_string(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_MATCH_THRESHOLD", "")
        assert _resolve_semantic_match_threshold() == 0.75


# ---------------------------------------------------------------------------
# skill_gap service - optional semantic-matching augmentation
#
# These tests inject a fake `semantic_matcher` (never call the real Gemini
# API), so they run offline and deterministically like everything else here.
# ---------------------------------------------------------------------------


class FakeMatcher(SemanticMatcher):
    """Test double implementing the `SemanticMatcher` interface.

    Wraps a plain function so each test can express its fake behavior
    concisely, while still exercising the real `.match()` contract that
    `skill_gap.py` depends on (not a bare callable).
    """

    def __init__(self, result_fn):
        self._result_fn = result_fn

    def match(self, candidate_skills, required_skills) -> SemanticMatchResult:
        return self._result_fn(candidate_skills, required_skills)


class TestAnalyzeSkillGapSemanticMatching:
    def test_default_behavior_is_unchanged_when_flag_is_off(self):
        # use_semantic_matching defaults to False - the matcher must
        # never even be constructed/called.
        def _boom(held, required):
            raise AssertionError("semantic matcher should not be called")

        profile = Profile(user_id="u1", skills=["Python"], target_role="Backend Dev")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["Python", "REST APIs"],
            semantic_matcher=FakeMatcher(_boom),
        )
        assert [g.skill for g in gap.gaps] == ["REST APIs"]

    def test_high_confidence_semantic_match_moves_skill_out_of_gaps(self):
        def fake_matcher(held, required):
            return SemanticMatchResult.model_validate(
                {
                    "matched_skills": [
                        {
                            "required_skill": "REST APIs",
                            "candidate_skill": "FastAPI",
                            "confidence": 0.95,
                            "reason": "FastAPI is used to build REST APIs.",
                        }
                    ]
                }
            )

        profile = Profile(user_id="u1", skills=["FastAPI"], target_role="Backend Dev")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["FastAPI", "REST APIs"],
            use_semantic_matching=True,
            semantic_matcher=FakeMatcher(fake_matcher),
        )

        assert gap.gaps == []
        assert "REST APIs" in gap.matched_skills

    def test_low_confidence_partial_match_stays_a_gap_with_richer_reason(self):
        def fake_matcher(held, required):
            return SemanticMatchResult.model_validate(
                {
                    "partially_matched": [
                        {
                            "required_skill": "Data Analysis",
                            "candidate_skill": "Pandas",
                            "confidence": 0.5,
                            "reason": "Pandas supports but doesn't fully cover data analysis.",
                        }
                    ]
                }
            )

        profile = Profile(user_id="u1", skills=["Pandas"], target_role="Data Analyst")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["Pandas", "Data Analysis"],
            use_semantic_matching=True,
            semantic_matcher=FakeMatcher(fake_matcher),
        )

        assert [g.skill for g in gap.gaps] == ["Data Analysis"]
        assert "Pandas" in gap.gaps[0].reason
        assert "Data Analysis" not in gap.matched_skills
        assert gap.gaps[0].priority == 1

    def test_priorities_stay_contiguous_after_removing_matched_gaps(self):
        def fake_matcher(held, required):
            return SemanticMatchResult.model_validate(
                {
                    "matched_skills": [
                        {
                            "required_skill": "REST APIs",
                            "candidate_skill": "FastAPI",
                            "confidence": 0.9,
                            "reason": "equivalent",
                        }
                    ]
                }
            )

        profile = Profile(user_id="u1", skills=["FastAPI"], target_role="Backend Dev")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["REST APIs", "Docker", "Kubernetes"],
            use_semantic_matching=True,
            semantic_matcher=FakeMatcher(fake_matcher),
        )

        gap_skills = [g.skill for g in gap.gaps]
        assert gap_skills == ["Docker", "Kubernetes"]
        assert [g.priority for g in gap.gaps] == [1, 2]

    def test_falls_back_gracefully_when_matcher_returns_empty_result(self):
        def fake_matcher(held, required):
            return empty_result()

        profile = Profile(user_id="u1", skills=["Python"], target_role="Backend Dev")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["Python", "Docker"],
            use_semantic_matching=True,
            semantic_matcher=FakeMatcher(fake_matcher),
        )

        # Identical to the deterministic-only result - Gemini found nothing.
        assert [g.skill for g in gap.gaps] == ["Docker"]

    def test_matcher_is_not_called_when_there_are_no_gaps(self):
        def _boom(held, required):
            raise AssertionError("semantic matcher should not be called when there are no gaps")

        profile = Profile(user_id="u1", skills=["Python", "Docker"], target_role="Backend Dev")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["Python", "Docker"],
            use_semantic_matching=True,
            semantic_matcher=FakeMatcher(_boom),
        )
        assert gap.gaps == []

    def test_default_matcher_is_a_gemini_matcher_instance(self, monkeypatch):
        # When use_semantic_matching=True and no matcher is injected,
        # skill_gap.py must default to the GeminiMatcher provider - and
        # nothing else - without ever being told "Gemini" explicitly by
        # the caller. This exercises analyze_skill_gap end-to-end with
        # no GEMINI_API_KEY set, so GeminiMatcher itself degrades to an
        # empty result (see gemini_matcher tests for that in isolation).
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        profile = Profile(user_id="u1", skills=["Python"], target_role="Backend Dev")
        gap = analyze_skill_gap(
            profile,
            required_skills_override=["Python", "Docker"],
            use_semantic_matching=True,
        )
        assert [g.skill for g in gap.gaps] == ["Docker"]


# ---------------------------------------------------------------------------
# skill_gap route
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(skill_gap_router)
    return TestClient(app)


class TestSkillGapRoute:
    def test_analyze_with_job_postings_returns_200_and_gaps(self, client: TestClient):
        payload = {
            "user_id": "u123",
            "target_role": "Data Analyst",
            "skills": ["Python", "excel"],
            "job_postings_skills": [["Python", "SQL", "Power BI"]],
        }

        response = client.post("/skill-gap/analyze", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == "u123"
        assert body["target_role"] == "Data Analyst"
        assert "Python" in body["matched_skills"]
        gap_skills = [g["skill"] for g in body["gaps"]]
        assert "SQL" in gap_skills
        assert "Power BI" in gap_skills
        # Every gap must carry a human-readable reason (transparency requirement).
        assert all(g["reason"] for g in body["gaps"])

    def test_analyze_with_required_skills_override(self, client: TestClient):
        payload = {
            "user_id": "u456",
            "target_role": "Backend Engineer",
            "skills": ["Python"],
            "required_skills": ["Python", "Docker", "Kubernetes"],
        }

        response = client.post("/skill-gap/analyze", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["required_skills"] == ["Python", "Docker", "Kubernetes"]
        gap_skills = [g["skill"] for g in body["gaps"]]
        assert gap_skills == ["Docker", "Kubernetes"]

    def test_analyze_with_semantic_matching_flag_falls_back_without_gemini_configured(
        self, client: TestClient, monkeypatch
    ):
        # No GEMINI_API_KEY set in this test environment -> gemini_matcher
        # degrades to empty_result() -> route still returns 200 with the
        # deterministic-only gaps, never an error.
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        payload = {
            "user_id": "u999",
            "target_role": "Backend Engineer",
            "skills": ["Python"],
            "required_skills": ["Python", "Docker"],
            "use_semantic_matching": True,
        }

        response = client.post("/skill-gap/analyze", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert [g["skill"] for g in body["gaps"]] == ["Docker"]

    def test_analyze_without_any_requirement_source_returns_400(self, client: TestClient):
        payload = {
            "user_id": "u789",
            "target_role": "Analyst",
            "skills": ["Python"],
        }

        response = client.post("/skill-gap/analyze", json=payload)

        assert response.status_code == 400
        assert "job_postings_skills" in response.json()["detail"]
