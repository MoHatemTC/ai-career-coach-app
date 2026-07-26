from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.services.database import get_db
from backend.models.db_models import JobPostingORM
from backend.features.matching.scorer import get_model

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

def save_fetched_jobs(fetched_jobs, db: Session):
    model = get_model()
    
    for job in fetched_jobs:
        text_to_embed = f"{job.title} {job.description} {' '.join(job.required_skills)}"
        job_embedding = model.encode(text_to_embed).tolist()
        
        db_job = JobPostingORM(
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            required_skills=job.required_skills,
            min_experience=job.min_experience,
            description=job.description,
            location=job.location,
            work_type=job.work_type,
            salary=job.salary,
            embedding=job_embedding
        )
        db.add(db_job)
        
    db.commit()