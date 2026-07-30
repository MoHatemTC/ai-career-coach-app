"""SQLAlchemy ORM layer for persisting ingested jobs.

`backend/models/job.py`'s `JobPosting` is the canonical Pydantic contract
shared by other lanes (matching, skill-gap) and must not change. This module
adds a *separate* ORM mirror plus conversion helpers, so persistence is an
additive concern that never alters the shared schema.

`JobPostingORM` mirrors `JobPosting`'s fields exactly, with two additions
(`created_at` / `updated_at`) and one storage adaptation: `skills` is a
JSON-encoded string, since SQLite has no native array type. `job_id` (the
deterministic sha256-of-URL from ingestion) is the primary key, which makes
dedup a direct primary-key lookup during upsert.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import declarative_base

from backend.models.job import JobPosting

Base = declarative_base()


class JobPostingORM(Base):
    """Persisted mirror of a `JobPosting`. Table: `job_postings`."""

    __tablename__ = "job_postings"

    # job_id is the deterministic sha256(url) hash from ingestion — using it as
    # the primary key makes upsert-by-job_id a direct PK lookup.
    job_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    skills = Column(Text, nullable=False, default="[]")  # JSON-encoded list
    job_type = Column(String, nullable=True)
    work_mode = Column(String, nullable=True)
    career_level = Column(String, nullable=True)
    experience_years = Column(String, nullable=True)
    salary = Column(String, nullable=True)
    source = Column(String, nullable=False)
    url = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IngestionRun(Base):
    """One ingestion run's lifecycle and outcome counts. Table: `ingestion_runs`.

    This is what the Streamlit dashboard polls to monitor a run in progress.
    """

    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    source = Column(String, nullable=False)  # requested sources, e.g. "arbeitnow,wuzzuf"
    jobs_fetched = Column(Integer, nullable=False, default=0)
    jobs_inserted = Column(Integer, nullable=False, default=0)
    jobs_updated = Column(Integer, nullable=False, default=0)
    jobs_skipped = Column(Integer, nullable=False, default=0)
    # Postings whose embedding reached the Qdrant vector store. Sits alongside
    # the other counters rather than being a new status value, so a lagging
    # count (jobs_embedded < inserted + updated) is visible without changing
    # the success/partial/failed contract.
    jobs_embedded = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="running")  # running|success|failed
    error_message = Column(Text, nullable=True)


class NotificationSettings(Base):
    """A user's notification preferences. Table: `notification_settings`.

    This is the store the notifications lane reads (Contract 6 in the pipeline
    plan: Omar's settings tab -> Ali's sender). Persisted to SQLite rather than
    held in a module-level dict so the values survive a backend restart, which
    is a real risk mid-demo, and so the notifications lane can read them
    without going through the UI process.

    Columns are flat even though the API serves `contact` as a nested object.
    Flat columns are what SQLite can index and query; the nesting is a
    presentation detail of the contract, applied at the route boundary.
    """

    __tablename__ = "notification_settings"

    user_id = Column(String, primary_key=True)
    email = Column(String, nullable=True)
    # The contract calls this phone_whatsapp; the column keeps the shorter name
    # it was created with so existing rows are unaffected.
    phone = Column(String, nullable=True)
    # JSON-encoded list, same approach as JobPostingORM.skills: SQLite has no
    # array type and a separate table for two enum-ish values is not worth it.
    notification_channels = Column(Text, nullable=True)
    frequency = Column(String, nullable=True)
    relevance_threshold = Column(Float, nullable=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def job_posting_to_orm(job: JobPosting) -> JobPostingORM:
    """Convert a validated `JobPosting` into a `JobPostingORM` row.

    `skills` is JSON-encoded for the Text column; every other field maps
    across directly.
    """
    return JobPostingORM(
        job_id=job.job_id,
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description,
        skills=json.dumps(job.skills),
        job_type=job.job_type,
        work_mode=job.work_mode,
        career_level=job.career_level,
        experience_years=job.experience_years,
        salary=job.salary,
        source=job.source,
        url=job.url,
        date=job.date,
    )


def orm_to_job_posting(row: JobPostingORM) -> JobPosting:
    """Convert a persisted `JobPostingORM` row back into a `JobPosting`.

    `skills` is JSON-decoded back into a list; falls back to an empty list
    if the stored value is somehow not valid JSON.
    """
    try:
        skills = json.loads(row.skills) if row.skills else []
    except (json.JSONDecodeError, TypeError):
        skills = []

    return JobPosting(
        job_id=row.job_id,
        title=row.title,
        company=row.company,
        location=row.location,
        description=row.description,
        skills=skills,
        job_type=row.job_type,
        work_mode=row.work_mode,
        career_level=row.career_level,
        experience_years=row.experience_years,
        salary=row.salary,
        source=row.source,
        url=row.url,
        date=row.date,
    )
