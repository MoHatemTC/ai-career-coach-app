"""Skill-gap API route.

Purpose (PRD Section 7.6 / docs/api.md format):
Expose the skill-gap analyzer as an HTTP endpoint so the frontend
`SkillGapPanel` can request a gap analysis for a user's profile.

Per CONTRIBUTING.md "Code Organization Rules": routes handle
request/response only; all logic lives in
`backend.services.skill_gap.analyze_skill_gap`.

Integration note (Sprint 1):
This repo does not yet have a shared FastAPI app instance / app
factory (checked: no `backend/main.py` or app entrypoint exists yet -
see docs/tasks.md, "Create the first FastAPI app entry point" is still
an open backend task). This module exposes an `APIRouter` so whoever
creates the app entrypoint can `app.include_router(router)` without
this lane needing to own app wiring or app-startup concerns.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.profile import Profile
from backend.services.skill_gap import analyze_skill_gap

router = APIRouter(prefix="/skill-gap", tags=["skill-gap"])


class SkillGapRequest(BaseModel):
    """Request body for POST /skill-gap/analyze.

    Either `job_postings_skills` or `required_skills` must be provided
    (mirrors `analyze_skill_gap`'s two supported modes).
    """

    user_id: str
    target_role: Optional[str] = None
    experience_level: Optional[str] = None
    skills: List[str] = Field(default_factory=list, description="Raw skills held by the user")
    job_postings_skills: Optional[List[List[str]]] = Field(
        default=None,
        description="Raw skill lists, one per job posting, used as the demand signal.",
    )
    required_skills: Optional[List[str]] = Field(
        default=None,
        description="Explicit required-skill override, used instead of job postings.",
    )
    use_semantic_matching: bool = Field(
        default=False,
        description=(
            "If true, run an optional Gemini semantic-matching pass on top of "
            "the deterministic taxonomy comparison, to catch equivalences the "
            "static alias table doesn't know about yet (e.g. 'FastAPI' ~ 'REST "
            "API Development'). Defaults to false: the deterministic-only "
            "behavior is unchanged unless a caller opts in."
        ),
    )


class SkillGapItemResponse(BaseModel):
    skill: str
    category: Optional[str]
    priority: int
    reason: str


class SkillGapResponse(BaseModel):
    user_id: str
    target_role: str
    required_skills: List[str]
    held_skills: List[str]
    matched_skills: List[str]
    gaps: List[SkillGapItemResponse]


@router.post("/analyze", response_model=SkillGapResponse)
def analyze(request: SkillGapRequest) -> SkillGapResponse:
    """Analyze the skill gap for a user against a target role.

    Request body example:
        {
          "user_id": "u123",
          "target_role": "Data Analyst",
          "skills": ["Python", "excel"],
          "job_postings_skills": [["Python", "SQL", "Power BI"]]
        }

    Response example:
        {
          "user_id": "u123",
          "target_role": "Data Analyst",
          "required_skills": ["Python", "SQL", "Power BI"],
          "held_skills": ["Python", "Excel"],
          "matched_skills": ["Python"],
          "gaps": [
            {"skill": "SQL", "category": "language", "priority": 1,
             "reason": "..."},
            {"skill": "Power BI", "category": "tool", "priority": 2,
             "reason": "..."}
          ]
        }

    Error cases:
        400 - neither job_postings_skills nor required_skills supplied.
    """
    profile = Profile(
        user_id=request.user_id,
        skills=request.skills,
        target_role=request.target_role,
        experience_level=request.experience_level,
    )

    try:
        result = analyze_skill_gap(
            profile=profile,
            job_postings_skills=request.job_postings_skills,
            required_skills_override=request.required_skills,
            use_semantic_matching=request.use_semantic_matching,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SkillGapResponse(**result.to_dict())
