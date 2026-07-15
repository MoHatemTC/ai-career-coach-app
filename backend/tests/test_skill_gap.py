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
from backend.services.skill_gap import analyze_skill_gap
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

    def test_analyze_without_any_requirement_source_returns_400(self, client: TestClient):
        payload = {
            "user_id": "u789",
            "target_role": "Analyst",
            "skills": ["Python"],
        }

        response = client.post("/skill-gap/analyze", json=payload)

        assert response.status_code == 400
        assert "job_postings_skills" in response.json()["detail"]
