from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from backend.services.database import get_db
from backend.models.db_models import JobPostingORM
from backend.features.matching.scorer import get_model
from backend.services.ingestion import ArbeitnowIngestionClient

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

class IngestionRunOut(BaseModel):
    status: str
    jobs_count: int

@router.get("/jobs", response_model=List[dict])
def get_ingested_jobs(db: Session = Depends(get_db)):
    jobs = db.query(JobPostingORM).all()
    return [{"job_id": job.job_id, "title": job.title, "company": job.company} for job in jobs]

def save_fetched_jobs(fetched_jobs, db: Session):
    model = get_model()
    
    for job in fetched_jobs:
        text_to_embed = f"{job.title} {job.description} {' '.join(job.skills if hasattr(job, 'skills') else job.required_skills)}"
        job_embedding = model.encode(text_to_embed).tolist()
        
        db_job = JobPostingORM(
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            required_skills=job.skills if hasattr(job, 'skills') else job.required_skills,
            min_experience=getattr(job, 'min_experience', 0),
            description=job.description,
            location=job.location,
            work_type=getattr(job, 'work_type', None) or getattr(job, 'work_mode', 'Unknown'),
            salary=job.salary,
            embedding=job_embedding
        )
       
        db.merge(db_job)
        
    db.commit()

@router.post("/run", response_model=IngestionRunOut)
def run_ingestion(limit: int = 10, db: Session = Depends(get_db)):
    try:
        client = ArbeitnowIngestionClient()
        jobs = client.get_jobs(limit=limit)
        save_fetched_jobs(jobs, db)
        return {"status": "success", "jobs_count": len(jobs)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))