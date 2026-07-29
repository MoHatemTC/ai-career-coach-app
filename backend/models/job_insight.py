"""Job Insight data models (Week 3 - Skill Gap task).

Purpose:
The Matching & Ranking Engine already returns a ranked shortlist (today,
the Top 3) of jobs, each with its own already-computed `match_score`,
`matched_skills`, and `missing_skills` - see `backend/models/match_result.py`.
This module defines the small, explicit data contracts the new Job
Insight Agent (`backend/services/job_insight_agent.py`) needs to turn
that shortlist into a UI-ready, per-job annotation:

    - `MatchedJob`: one entry of the Matching Engine's shortlist - a
      `JobInfo` paired with the `MatchResult` already computed for it.
      This is the agent's INPUT contract; it introduces no new fields
      and no computation, it just bundles two existing models together
      so a list of them can be iterated as "the Top 3 matched jobs".
    - `JobFitInsight`: the agent's Gemini OUTPUT contract - exactly the
      three fields the task requires (`strength`, `weakness`,
      `recommendation`), each a short string. Deliberately smaller than
      `backend.services.match_explanation_agent.MatchExplanation` (which
      has five fields, some of them lists) - this is a compact,
      shortlist-card annotation, not a full explanation page.
    - `JobInsight`: the final, UI-ready record for one job - ALL of
      `MatchedJob`'s existing fields (job_id, title, company,
      required_skills, match_score, matched_skills, missing_skills),
      unchanged, plus the three new `JobFitInsight` fields appended.
      This is what satisfies "preserve all existing job fields and only
      append the three required fields".

Matches the pattern used by `backend/models/job.py`,
`backend/models/match_result.py`, and `backend/models/profile.py`:
plain dataclasses + `to_dict()`/`from_dict()`, no ORM/DB dependency
(this repo has no shared DB layer yet), except for `JobFitInsight`,
which is a Pydantic model for the same reason
`match_explanation_agent.MatchExplanation` is - it's the thing a raw
Gemini response gets validated against, and Pydantic is what the rest
of this codebase already uses for that specific job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.models.job import JobInfo
from backend.models.match_result import MatchResult


@dataclass
class MatchedJob:
    """One entry of the Matching & Ranking Engine's shortlist.

    Purely a pairing of two already-existing models - introduces no new
    fields and performs no computation. A list of `MatchedJob` is what
    "the Top 3 matched jobs with their match scores" means in code.

    Attributes:
        job: The job's information (title, company, required_skills, ...).
        match_result: The already-computed match result for this job
            (`match_score`, `matched_skills`, `missing_skills`) - treated
            as read-only, trusted input throughout the Job Insight Agent.
    """

    job: JobInfo
    match_result: MatchResult

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "job": {
                "job_id": self.job.job_id,
                "title": self.job.title,
                "company": self.job.company,
                "required_skills": list(self.job.required_skills),
            },
            "match_result": self.match_result.to_dict(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "MatchedJob":
        """Rebuild a MatchedJob from a plain dict (e.g. the Matching
        Engine's own output shape, or a request body)."""
        job_data = data["job"]
        return MatchedJob(
            job=JobInfo(
                job_id=job_data["job_id"],
                title=job_data["title"],
                company=job_data.get("company"),
                required_skills=list(job_data.get("required_skills", [])),
            ),
            match_result=MatchResult.from_dict(data["match_result"]),
        )


class JobFitInsight(BaseModel):
    """Validated shape of the Job Insight Agent's Gemini response.

    Exactly the three fields the Week 3 task requires - each a short,
    single string (not a list), which is what keeps this schema
    compact enough for a shortlist card rather than a full explanation
    page. Both have safe string defaults so a partially-populated
    response still validates instead of raising - see
    `job_insight_agent._try_parse_insight`.

    Attributes:
        strength: One short, specific reason this candidate fits the
            role, grounded only in `matched_skills` / the candidate
            profile - never invented.
        weakness: One short, specific gap for this role, grounded only
            in `missing_skills` - never invented.
        recommendation: One short, actionable suggestion for closing
            the gap or better presenting an existing strength.
    """

    strength: str = ""
    weakness: str = ""
    recommendation: str = ""


@dataclass
class JobInsight:
    """The final, UI-ready record for one job: all of its existing
    fields, unchanged, plus the three new insight fields appended.

    This is the literal implementation of "preserve all existing job
    fields and only append the three required fields" - every field
    below except `strength`/`weakness`/`recommendation` is copied
    as-is from the `MatchedJob` this was built from
    (`job_insight_agent.build_job_insight`); none of them are
    recomputed, and `match_score` in particular is never touched.

    Attributes:
        job_id: Copied from `MatchedJob.job.job_id`.
        title: Copied from `MatchedJob.job.title`.
        company: Copied from `MatchedJob.job.company`.
        required_skills: Copied from `MatchedJob.job.required_skills`.
        match_score: Copied from `MatchedJob.match_result.match_score` -
            never recalculated or modified by this feature.
        matched_skills: Copied from `MatchedJob.match_result.matched_skills`.
        missing_skills: Copied from `MatchedJob.match_result.missing_skills`.
        strength: The appended `JobFitInsight.strength`.
        weakness: The appended `JobFitInsight.weakness`.
        recommendation: The appended `JobFitInsight.recommendation`.
    """

    job_id: str
    title: str
    match_score: float
    company: Optional[str] = None
    required_skills: List[str] = field(default_factory=list)
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    strength: str = ""
    weakness: str = ""
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict, ready for an API
        response or direct use by a frontend."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "required_skills": self.required_skills,
            "match_score": self.match_score,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "strength": self.strength,
            "weakness": self.weakness,
            "recommendation": self.recommendation,
        }
