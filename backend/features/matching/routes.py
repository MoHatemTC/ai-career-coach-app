from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.services.database import get_db
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.models.profile import Profile
from backend.features.matching.scorer import calculate_match_score
from pydantic import BaseModel


router = APIRouter(tags=["Matching"])

class MatchRequest(BaseModel):
    profile: Profile

class RankedJobResponse(BaseModel):
    job_id: str
    title: str
    company: str
    match_score: float

@router.post("/rank-jobs", response_model=List[RankedJobResponse])
def rank_jobs_for_profile(request: MatchRequest, db: Session = Depends(get_db)):
    db_jobs = db.query(JobPostingORM).all()
    
    ranked_results = []
    for db_job in db_jobs:
        job_obj = orm_to_job_posting(db_job)
        score = calculate_match_score(request.profile, job_obj)
        
        ranked_results.append({
            "job_id": job_obj.job_id,
            "title": job_obj.title,
            "company": job_obj.company,
            "match_score": score
        })
    
    ranked_results.sort(key=lambda x: x["match_score"], reverse=True)
    
    return ranked_results