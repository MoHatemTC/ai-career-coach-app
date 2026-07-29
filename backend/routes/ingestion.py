"""HTTP routes for triggering and monitoring the ingestion pipeline.

Thin HTTP layer only — all business logic lives in
`backend/services/ingestion_pipeline.py`. `POST /ingestion/run` kicks the
pipeline off as a FastAPI `BackgroundTask` and returns a `run_id` immediately;
the other routes are read-only views the dashboard polls.
"""

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
