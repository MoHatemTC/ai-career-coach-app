from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from backend.services.database import get_db
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.features.matching.scorer import calculate_match_score
from backend.features.matching.schema import MatchRequest, RankedJobResponse

router = APIRouter(tags=["Matching"])

@router.post("/rank-jobs", response_model=List[RankedJobResponse])
def rank_jobs_for_profile(
    request: MatchRequest, 
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100)  
):
    db_jobs = db.query(JobPostingORM).limit(limit).all()
    
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
    
    ranked_results.sort(key=lambda x: (-x["match_score"], x["job_id"]))
    
    return ranked_results