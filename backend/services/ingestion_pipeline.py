"""Ingestion pipeline: fetch -> validate -> upsert -> record.

Orchestrates the ingestion clients, deduplicates by `job_id`, persists each
posting via upsert, and records the run's outcome in an `IngestionRun` row
the UI can poll.

Dedup strategy: the detection key is `job_id` (a deterministic sha256 of the
posting URL — the same posting always hashes the same). Resolution is an
upsert: a posting whose `job_id` is not yet stored is inserted; one that is
already stored is overwritten with the freshly ingested values, because a
re-scrape may carry a corrected description or an updated date, so each run is
treated as the source of truth.
"""

import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Union

from pydantic import ValidationError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.models.job import JobPosting
from backend.models.db_models import (
    IngestionRun,
    JobPostingORM,
    job_posting_to_orm,
)
from backend.services.database import SessionLocal
from backend.services.ingestion import (
    ArbeitnowIngestionClient,
    MockMenaIngestionClient,
    WuzzufScraperClient,
)

# Registry of supported source names -> client factory.
CLIENT_FACTORIES = {
    "arbeitnow": ArbeitnowIngestionClient,
    "wuzzuf": WuzzufScraperClient,
    "mock_mena": MockMenaIngestionClient,
}
DEFAULT_SOURCES = list(CLIENT_FACTORIES.keys())


def upsert_job_postings(
    session: Session,
    postings: Iterable[Union[JobPosting, dict]],
    run: IngestionRun,
) -> None:
    """Upsert each posting into `job_postings`, mutating the run's counters.

    Each item is validated defensively via `JobPosting.model_validate` — an
    already-valid `JobPosting` passes straight through, while a raw/invalid
    record is counted under `jobs_skipped` and never persisted (so one bad
    posting can't crash the batch). Valid postings are matched by `job_id`:
    missing -> insert (`jobs_inserted`), present -> overwrite (`jobs_updated`).
    """
    for item in postings:
        try:
            job = JobPosting.model_validate(item)
        except ValidationError:
            run.jobs_skipped += 1
            continue

        existing = session.get(JobPostingORM, job.job_id)
        new_row = job_posting_to_orm(job)
        if existing is None:
            session.add(new_row)
            run.jobs_inserted += 1
        else:
            # Overwrite every mutable field; the run is the source of truth.
            existing.title = new_row.title
            existing.company = new_row.company
            existing.location = new_row.location
            existing.description = new_row.description
            existing.skills = new_row.skills
            existing.job_type = new_row.job_type
            existing.work_mode = new_row.work_mode
            existing.career_level = new_row.career_level
            existing.experience_years = new_row.experience_years
            existing.salary = new_row.salary
            existing.source = new_row.source
            existing.url = new_row.url
            existing.date = new_row.date
            run.jobs_updated += 1


def _resolve_sources(sources: Optional[List[str]]) -> List[str]:
    """Normalize a requested source list, defaulting to all known sources."""
    if not sources:
        return list(DEFAULT_SOURCES)
    return [s for s in sources if s in CLIENT_FACTORIES]


def run_ingestion(
    sources: Optional[List[str]] = None,
    limit: int = 10,
    run_id: Optional[int] = None,
    session: Optional[Session] = None,
) -> IngestionRun:
    """Run ingestion for the requested sources and record the outcome.

    If `run_id` is given, the existing (already `running`) row is loaded and
    finalized — this is the path used by the API's background task, so the
    route can return the id immediately. If omitted, a fresh run row is
    created, executed, and finalized synchronously (used by tests and direct
    callers). Returns the finalized `IngestionRun`.

    Failure handling — each source's fetch+upsert cycle runs in its own
    try/except and its own transaction (commit per source). A source that
    raises (e.g. Arbeitnow's unguarded `raise_for_status` on a network error)
    is rolled back, logged, recorded in `error_message`, and the run moves on
    to the next source rather than aborting — so one flaky source never leaves
    the row stuck at `status="running"`. Final status is a deliberate choice:

    - ``success`` — every requested source completed.
    - ``partial`` — at least one source succeeded and at least one failed.
    - ``failed``  — every source failed (or a catastrophic error occurred).
    """
    resolved = _resolve_sources(sources)

    owns_session = session is None
    session = session or SessionLocal()
    try:
        if run_id is not None:
            run = session.get(IngestionRun, run_id)
            if run is None:
                logger.error("run_ingestion called with unknown run_id=%s", run_id)
                return None
        else:
            run = IngestionRun(
                started_at=datetime.now(timezone.utc),
                source=",".join(resolved),
                status="running",
            )
            session.add(run)
            session.commit()

        failures: List[str] = []
        for name in resolved:
            try:
                client = CLIENT_FACTORIES[name]()
                jobs = client.get_jobs(limit=limit)
                run.jobs_fetched += len(jobs)
                upsert_job_postings(session, jobs, run)
                session.commit()
            except Exception as exc:  # noqa: BLE001 - isolate & record per-source failure
                # Rollback discards this source's uncommitted counter bumps and
                # partial batch; earlier sources' commits are untouched.
                session.rollback()
                logger.exception("Ingestion source %r failed", name)
                failures.append(f"{name}: {exc}")

        run.finished_at = datetime.now(timezone.utc)
        if not failures:
            run.status = "success"
        elif len(failures) < len(resolved):
            run.status = "partial"
            run.error_message = "; ".join(failures)
        else:
            run.status = "failed"
            run.error_message = "; ".join(failures)
        session.commit()
        session.refresh(run)
        return run
    except Exception as exc:  # noqa: BLE001 - catastrophic (e.g. run row couldn't commit)
        session.rollback()
        logger.exception("run_ingestion failed catastrophically")
        run = locals().get("run")
        if run is not None and run.id is not None:
            run.finished_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.error_message = str(exc)
            session.commit()
            session.refresh(run)
            return run
        raise
    finally:
        if owns_session:
            session.close()
