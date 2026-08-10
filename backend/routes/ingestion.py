"""HTTP routes for triggering and monitoring the ingestion pipeline.

Thin HTTP layer only — all business logic lives in
`backend/services/ingestion_pipeline.py`. `POST /ingestion/run` kicks the
pipeline off as a FastAPI `BackgroundTask` and returns a `run_id` immediately;
the other routes are read-only views the dashboard polls.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.models.db_models import (
    IngestionRun,
    JobPostingORM,
    orm_to_job_posting,
)
from backend.models.job import JobPosting
from backend.services.database import get_db
from backend.services.ingestion_pipeline import (
    DEFAULT_SOURCES,
    _resolve_sources,
    run_ingestion,
)

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


class RunIngestionRequest(BaseModel):
    sources: Optional[List[str]] = None  # subset of DEFAULT_SOURCES; None -> all
    limit: int = 10


class RunIngestionResponse(BaseModel):
    run_id: int


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: Optional[datetime]
    source: str
    jobs_fetched: int
    jobs_inserted: int
    jobs_updated: int
    jobs_skipped: int
    jobs_embedded: int
    status: str
    error_message: Optional[str]


@router.post("/run", response_model=RunIngestionResponse, status_code=202)
def trigger_ingestion(
    request: RunIngestionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RunIngestionResponse:
    """Kick off an ingestion run in the background, returning its id at once."""
    resolved = _resolve_sources(request.sources)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail=f"No valid sources requested. Choose from {DEFAULT_SOURCES}.",
        )

    # Pre-create the run row so GET /runs/{id} resolves immediately while the
    # background task does the actual fetching/upserting.
    run = IngestionRun(
        started_at=datetime.now(timezone.utc),
        source=",".join(resolved),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(
        run_ingestion, sources=resolved, limit=request.limit, run_id=run.id
    )
    return RunIngestionResponse(run_id=run.id)


@router.get("/runs/{run_id}", response_model=IngestionRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)) -> IngestionRun:
    """Current status/counts for a single run (what the dashboard polls)."""
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return run


@router.get("/runs", response_model=List[IngestionRunOut])
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[IngestionRun]:
    """The most recent runs, newest first."""
    return (
        db.query(IngestionRun)
        .order_by(IngestionRun.id.desc())
        .limit(limit)
        .all()
    )


class TagCount(BaseModel):
    label: str
    count: int


class SourceCount(BaseModel):
    name: str
    count: int


class PoolStats(BaseModel):
    """A read-only snapshot of what has actually been ingested.

    Every number here is counted from `job_postings` at request time. Nothing
    is estimated, cached, or rounded up — the landing page renders this as
    evidence that the pipeline is real, so a figure that drifted from the
    table would be worse than showing nothing.
    """

    total_postings: int
    distinct_tags: int
    sources: List[SourceCount]
    top_tags: List[TagCount]
    last_ingested_at: Optional[datetime]


@router.get("/stats", response_model=PoolStats)
def pool_stats(
    top: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> PoolStats:
    """Aggregate view of the job pool, for the landing page's live snapshot.

    `top_tags` are the source's own category tags, counted across postings —
    NOT extracted skills. Arbeitnow publishes values like "engineering" and
    "marketing", which describe a whole job family rather than a competency,
    so anything rendering this must label it as a category. Calling them
    skills would overstate what the number means.

    Counting happens in Python rather than SQL because `skills` is a
    JSON-encoded string in SQLite (see `db_models.JobPostingORM`), so there is
    no array to GROUP BY. At a few hundred postings this is not worth a schema
    change; if the pool reaches five figures, normalise the tags into their own
    table rather than making this query cleverer.
    """
    rows = db.query(JobPostingORM.skills, JobPostingORM.source).all()

    tag_counts: Counter = Counter()
    source_counts: Counter = Counter()
    for raw_skills, source in rows:
        source_counts[source or "unknown"] += 1
        try:
            tags = json.loads(raw_skills or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(tags, list):
            continue
        # De-duplicated per posting: a posting that lists a tag twice should
        # count once, or the totals stop being "postings mentioning X".
        seen = {
            str(tag).strip().lower() for tag in tags if str(tag).strip()
        }
        tag_counts.update(seen)

    last_run = (
        db.query(IngestionRun)
        .filter(IngestionRun.finished_at.isnot(None))
        .order_by(IngestionRun.finished_at.desc())
        .first()
    )

    return PoolStats(
        total_postings=len(rows),
        distinct_tags=len(tag_counts),
        sources=[
            SourceCount(name=name, count=count)
            for name, count in source_counts.most_common()
        ],
        top_tags=[
            TagCount(label=label, count=count)
            for label, count in tag_counts.most_common(top)
        ],
        last_ingested_at=last_run.finished_at if last_run else None,
    )


@router.get("/jobs", response_model=List[JobPosting])
def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[JobPosting]:
    """Persisted job postings, most recent first, paginated."""
    rows = (
        db.query(JobPostingORM)
        .order_by(JobPostingORM.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [orm_to_job_posting(row) for row in rows]
