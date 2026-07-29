"""Canonical shared JobPosting model, plus the explanation lane's JobInfo view.

`JobPosting` is THE shared job schema for the whole project. Every lane that
consumes job postings (ingestion, matching, ranking, skill-gap analysis,
frontend serialization) imports it from this module rather than redefining its
own copy — duplicated schemas have already caused field-name drift between
lanes more than once.

Field notes:
- `skills` contains real skills only. Job-type / work-mode / seniority
  chips that sources mix into their tag lists are routed into the
  dedicated metadata fields below by the ingestion clients
  (see `backend/services/ingestion.py`).
- `job_id` is a deterministic sha256 hash of the posting URL, so the
  same posting always gets the same id across runs (safe for caching
  and deduplication).

Need a field that doesn't exist yet? Open a GitHub Issue tagged
`ingestion` describing the field and which lane consumes it, or raise
it in the team chat — don't fork the model. Additions land here via a
reviewed PR so every lane picks them up at once.

`JobInfo` is a separate, smaller dataclass owned by the Match Explanation
Agent lane. It is NOT a replacement for `JobPosting` — it is the reduced view
that agent reads (job_id / title / company / required_skills). Both classes
live here because they describe the same domain object, and removing either
breaks a lane: eleven modules import `JobPosting` from this file, and the
explanation agent imports `JobInfo`. Use `JobInfo.from_job_posting` to go from
the canonical model to the reduced one rather than constructing it by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


class JobPosting(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    description: str
    skills: List[str]          # only real skills now
    job_type: Optional[str] = None      # "Full Time", "Part Time"
    work_mode: Optional[str] = None     # "On-site", "Remote", "Hybrid"
    career_level: Optional[str] = None  # "Manager", "Experienced", "Entry"
    experience_years: Optional[str] = None  # raw range string, e.g. "5 - 10 Yrs"
    salary: Optional[str] = None
    source: str
    url: str
    date: datetime

    @field_validator("title", "company")
    @classmethod
    def not_blank(cls, value: str, info):
        if not value or not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str):
        if not value.startswith("http"):
            raise ValueError("url must start with http")
        return value


@dataclass
class JobInfo:
    """Minimal job contract consumed by the Match Explanation Agent.

    Attributes:
        job_id: Identifier of the job posting.
        title: Job title (e.g. "Backend Developer").
        company: Employer name, if known.
        required_skills: Canonical skills required for the role, as
            already determined upstream (Job Parser + Skill Gap
            Analyzer) - the explanation agent never derives these
            itself.
    """

    job_id: str
    title: str
    company: Optional[str] = None
    required_skills: List[str] = field(default_factory=list)

    @classmethod
    def from_job_posting(cls, posting: JobPosting) -> "JobInfo":
        """Narrow a canonical `JobPosting` down to what the agent reads.

        Exists so the explanation lane never has to know how the ingestion
        lane spells its fields — `skills` here, `required_skills` there.
        """
        return cls(
            job_id=posting.job_id,
            title=posting.title,
            company=posting.company,
            required_skills=list(posting.skills),
        )
