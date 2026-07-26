from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
)

from backend.services.database import Base
from backend.models.job import JobPosting as CanonicalJobPosting
from backend.models.job_posting import JobPosting


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobPostingORM(Base):
    __tablename__ = "job_postings"

    job_id = Column(String, primary_key=True, index=True)
    title = Column(String)
    company = Column(String)
    required_skills = Column(JSON, default=[])
    min_experience = Column(Integer, default=0)
    description = Column(String, default="")
    location = Column(String, default="")
    work_type = Column(String, default="")
    salary = Column(Integer, default=0)

    # --- Canonical-schema columns (backend/models/job.py) -------------------
    # The legacy columns above match backend/models/job_posting.py, which is
    # what the matching lane imports today. backend/models/job.py documents
    # itself as THE shared schema and is what the ingestion lane writes, so
    # the two drifted. Rather than break the matching lane mid-sprint, these
    # columns are added additively and `orm_to_canonical_job()` reads them,
    # falling back to the legacy columns when a row predates ingestion.
    #
    # ACTION (Mohamed Farag): once refactor/align-job-schema merges and the
    # canonical schema is confirmed, the legacy columns above can be dropped
    # and the fallbacks in orm_to_canonical_job() deleted.
    skills = Column(JSON, default=[])
    job_type = Column(String, nullable=True)
    work_mode = Column(String, nullable=True)
    career_level = Column(String, nullable=True)
    experience_years_raw = Column(String, nullable=True)
    salary_text = Column(String, nullable=True)
    source = Column(String, default="internal")
    url = Column(String, nullable=True)
    date = Column(DateTime, default=_utcnow, index=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    status = Column(String, default="completed")


class UserORM(Base):
    """A person who receives digests.

    Holds contact channels + a profile snapshot. See backend/models/user.py
    for why the profile lives here for now and how to migrate it out.
    """

    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)
    full_name = Column(String, default="")

    # Contact channels
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)  # stored E.164

    # Delivery preferences
    notifications_enabled = Column(Boolean, default=True, nullable=False)
    notify_via_whatsapp = Column(Boolean, default=True, nullable=False)
    notify_via_email = Column(Boolean, default=True, nullable=False)
    min_match_score = Column(Float, default=40.0, nullable=False)
    send_hour_local = Column(Integer, default=8, nullable=False)
    timezone = Column(String, default="Africa/Cairo", nullable=False)

    # Profile snapshot (mirrors backend/models/profile.py)
    current_title = Column(String, default="")
    skills = Column(JSON, default=[])
    experience_years = Column(Integer, default=0)
    summary = Column(String, default="")
    location = Column(String, default="")
    preferred_work_type = Column(String, default="")
    salary_expectation = Column(Integer, default=0)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class NotificationLogORM(Base):
    """One row per delivery attempt, per channel.

    Serves three jobs at once:
      * de-duplication — PRD 7.9 (S) says don't re-notify about jobs the user
        already saw, so the dispatcher reads back recent `job_ids`;
      * idempotency — a scheduler that fires twice (restart, overlapping run)
        must not double-send, so `sent_on_local_date` is checked first;
      * debugging — when a user says "I got nothing", `status` + `error`
        answers whether we tried, and what the provider said.
    """

    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    channel = Column(String, nullable=False)  # "whatsapp" | "email"
    provider = Column(String, nullable=True)  # "postpeer" | "smtp" | ...
    status = Column(String, nullable=False)  # "sent" | "failed" | "skipped"

    job_ids = Column(JSON, default=[])
    match_scores = Column(JSON, default=[])

    provider_message_id = Column(String, nullable=True)
    error_message = Column(String, nullable=True)

    # Local calendar date (YYYY-MM-DD) in the user's timezone. The idempotency
    # key is (user_id, channel, sent_on_local_date) — a UTC timestamp alone
    # would let a user in UTC+2 get two digests on the same local day.
    sent_on_local_date = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow, index=True)


def orm_to_job_posting(orm_obj: JobPostingORM) -> JobPosting:
    """Legacy adapter — unchanged, still used by the matching lane."""
    return JobPosting(
        job_id=orm_obj.job_id,
        title=orm_obj.title,
        company=orm_obj.company,
        required_skills=orm_obj.required_skills or [],
        min_experience=orm_obj.min_experience or 0,
        description=orm_obj.description or "",
        location=orm_obj.location or "",
        work_type=orm_obj.work_type or "",
        salary=orm_obj.salary or 0,
    )


def orm_to_canonical_job(
    orm_obj: JobPostingORM,
    fallback_url_base: str = "",
) -> CanonicalJobPosting | None:
    """Adapt a row to the canonical `backend/models/job.py` schema.

    Returns `None` instead of raising when a row can't satisfy the canonical
    validators. A single malformed row must not abort a nightly run for every
    user — the caller skips it and keeps going.

    `fallback_url_base` is used only when a row has no `url` (rows seeded
    before the ingestion lane existed). We deliberately point at our own app
    rather than fabricating an external link, so a digest never sends the user
    to a URL that does not exist.
    """
    skills = orm_obj.skills or orm_obj.required_skills or []

    url = (orm_obj.url or "").strip()
    if not url.startswith("http"):
        if not fallback_url_base:
            return None
        url = f"{fallback_url_base.rstrip('/')}/jobs/{orm_obj.job_id}"

    salary = orm_obj.salary_text
    if not salary and orm_obj.salary:
        salary = str(orm_obj.salary)

    experience = orm_obj.experience_years_raw
    if not experience and orm_obj.min_experience:
        experience = f"{orm_obj.min_experience}+ Yrs"

    try:
        return CanonicalJobPosting(
            job_id=orm_obj.job_id,
            title=orm_obj.title or "",
            company=orm_obj.company or "Unknown Company",
            location=orm_obj.location or "",
            description=orm_obj.description or "",
            skills=list(skills),
            job_type=orm_obj.job_type,
            work_mode=orm_obj.work_mode or orm_obj.work_type or None,
            career_level=orm_obj.career_level,
            experience_years=experience,
            salary=salary,
            source=orm_obj.source or "internal",
            url=url,
            date=orm_obj.date or _utcnow(),
        )
    except Exception:
        # Canonical validators reject blank title/company. Skip the row.
        return None
