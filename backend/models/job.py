"""Canonical shared JobPosting model.

This is THE shared job schema for the whole project. Every lane that
consumes job postings (matching, skill-gap analysis, recommendations,
frontend serialization) should import `JobPosting` from this module
rather than redefining its own copy — duplicated schemas have already
caused field-name drift between lanes once.

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
"""

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
