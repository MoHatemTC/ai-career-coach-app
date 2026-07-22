from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from backend.models.db_models import IngestionRun, JobPostingORM, orm_to_job_posting
from backend.models.job_posting import JobPosting
from backend.services.database import get_db

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

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

@router.get("/jobs", response_model=List[JobPosting])
def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[JobPosting]:
    rows = (
        db.query(JobPostingORM)
        .order_by(JobPostingORM.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [orm_to_job_posting(row) for row in rows]