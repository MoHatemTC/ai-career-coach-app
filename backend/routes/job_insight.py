"""Job Insight API route (Week 3 - Skill Gap task).

Purpose:
Expose the Job Insight Agent
(`backend.services.job_insight_agent`) as an HTTP endpoint, so the
frontend can request strength/weakness/recommendation annotations for
the Matching & Ranking Engine's already-computed Top-3 shortlist, and
get back both the augmented jobs list and a UI-ready summary in one
response.

Per CONTRIBUTING.md "Code Organization Rules": routes handle
request/response only; all logic - including the batch loop over the
shortlist and the summary formatting - lives in
`backend.services.job_insight_agent.generate_job_insights`. This
handler does exactly three things: receive the request, call that one
service method, return its result.

Integration note:
Like `backend/routes/skill_gap.py`, this repo does not yet have a
shared FastAPI app instance / app factory. This module exposes an
`APIRouter` so whoever creates the app entrypoint can
`app.include_router(router)` without this lane needing to own app
wiring or app-startup concerns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.models.job import JobInfo
from backend.models.job_insight import MatchedJob
from backend.models.match_result import MatchResult
from backend.models.profile import Profile
from backend.services.job_insight_agent import generate_job_insights

router = APIRouter(prefix="/job-insight", tags=["job-insight"])


class MatchedJobRequest(BaseModel):
    """One entry of the Matching Engine's already-computed shortlist.

    Mirrors `backend.models.job_insight.MatchedJob` exactly - this
    route performs no matching or scoring of its own, it only accepts
    what the Matching Engine already produced.
    """

    job_id: str
    title: str
    company: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    match_score: float
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)


class TopMatchesInsightRequest(BaseModel):
    """Request body for POST /job-insight/top-matches."""

    user_id: str
    target_role: Optional[str] = None
    experience_level: Optional[str] = None
    skills: List[str] = Field(default_factory=list, description="Raw skills held by the user")
    matched_jobs: List[MatchedJobRequest] = Field(
        description="The Matching Engine's already-ranked shortlist (today, the Top 3)."
    )


class TopMatchesInsightResponse(BaseModel):
    """Response body for POST /job-insight/top-matches.

    Deliberately untyped-past-the-top-level (`Dict[str, Any]` for each
    job / for `ui_summary`) rather than re-declaring
    `backend.models.job_insight.JobInsight` and
    `job_insight_agent.build_ui_summary`'s shapes as a second set of
    Pydantic models here - that would be exactly the kind of duplicated
    business-logic-shape this refactor is meant to avoid. The service
    layer (`generate_job_insights`) is the single source of truth for
    both shapes; this model only documents the two top-level keys.
    """

    augmented_jobs: List[Dict[str, Any]] = Field(
        description=(
            "One entry per shortlisted job, preserving all of its existing "
            "fields (job_id, title, company, required_skills, match_score, "
            "matched_skills, missing_skills) plus the appended strength/"
            "weakness/recommendation - see backend.models.job_insight.JobInsight."
        )
    )
    ui_summary: Dict[str, Any] = Field(
        description=(
            "The same jobs, pre-formatted for direct UI rendering - see "
            "backend.services.job_insight_agent.build_ui_summary."
        )
    )


@router.post("/top-matches", response_model=TopMatchesInsightResponse)
def top_matches_insight(request: TopMatchesInsightRequest) -> TopMatchesInsightResponse:
    """Receive the shortlist, delegate to the Job Insight Agent service,
    and return its result.

    Per CONTRIBUTING.md "Code Organization Rules", this handler holds
    no business logic of its own: it only translates the request body
    into the service's input models (`Profile` / `MatchedJob` - plain
    data, no computation) and translates
    `job_insight_agent.generate_job_insights`'s return value into the
    response body. All annotation logic (Gemini calls, retries,
    completeness validation, fallback, summary formatting) lives in
    `backend.services.job_insight_agent`.

    Request body example:
        {
          "user_id": "u123",
          "target_role": "Backend Developer",
          "skills": ["Python", "FastAPI", "Docker"],
          "matched_jobs": [
            {
              "job_id": "job-1", "title": "Backend Developer",
              "company": "Acme Corp",
              "required_skills": ["Python", "REST APIs", "Docker", "PostgreSQL"],
              "match_score": 82,
              "matched_skills": ["Python", "Docker"],
              "missing_skills": ["REST APIs", "PostgreSQL"]
            }
          ]
        }

    Response shape: `augmented_jobs` (see
    `backend.models.job_insight.JobInsight.to_dict`) and `ui_summary`
    (see `backend.services.job_insight_agent.build_ui_summary`).
    """
    profile = Profile(
        user_id=request.user_id,
        skills=request.skills,
        target_role=request.target_role,
        experience_level=request.experience_level,
    )

    matched_jobs = [
        MatchedJob(
            job=JobInfo(
                job_id=item.job_id,
                title=item.title,
                company=item.company,
                required_skills=item.required_skills,
            ),
            match_result=MatchResult(
                match_score=item.match_score,
                matched_skills=item.matched_skills,
                missing_skills=item.missing_skills,
            ),
        )
        for item in request.matched_jobs
    ]

    augmented_jobs, ui_summary = generate_job_insights(profile, matched_jobs)

    return TopMatchesInsightResponse(
        augmented_jobs=[job.to_dict() for job in augmented_jobs],
        ui_summary=ui_summary,
    )
