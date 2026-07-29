from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.services.database import get_db
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.models.profile import Profile
from backend.features.matching.scorer import calculate_match_score
from backend.features.matching.retriever import retrieve_top_jobs  
from pydantic import BaseModel


router = APIRouter(tags=["Matching"])

class MatchRequest(BaseModel):
    profile: Profile
    top_k: Optional[int] = 10 

class RankedJobResponse(BaseModel):
    job_id: str
    title: str
    company: str
    location: Optional[str] = None
    work_type: Optional[str] = None
    salary: Optional[str] = None
    match_score: float
    description: Optional[str] = None

@router.post("/rank-jobs", response_model=List[RankedJobResponse])
def rank_jobs_for_profile(request: MatchRequest, db: Session = Depends(get_db)):
   
    profile_text = f"{request.profile.summary if hasattr(request.profile, 'summary') else ''} " \
                   f"{' '.join(request.profile.skills) if hasattr(request.profile, 'skills') else ''}"
    
    if not profile_text.strip():
        profile_text = str(request.profile)

    try:
        # retrieve_top_jobs queries Qdrant, not SQL — it takes no session.
        # Passing db= raised TypeError, which the except below swallowed, so
        # the RAG path never actually ran.
        ranked_results = retrieve_top_jobs(cv_text=profile_text, top_k=request.top_k)
        
        formatted_results = []
        for job in ranked_results:
            formatted_results.append({
                "job_id": job["job_id"],
                "title": job["title"],
                "company": job["company"],
                "location": job.get("location"),
                "work_type": job.get("work_type"),
                "salary": job.get("salary"),
                "match_score": job["match_score"],
                "description": job.get("description")
            })
            
        return formatted_results

    except Exception as e:
        db_jobs = db.query(JobPostingORM).all()
        ranked_results = []
        for db_job in db_jobs:
            job_obj = orm_to_job_posting(db_job)
            score = calculate_match_score(request.profile, job_obj)
            ranked_results.append({
                "job_id": job_obj.job_id,
                "title": job_obj.title,
                "company": job_obj.company,
                "location": getattr(job_obj, 'location', None),
                "work_type": getattr(job_obj, 'work_type', None),
                "salary": getattr(job_obj, 'salary', None),
                "match_score": score,
                "description": getattr(job_obj, 'description', None)
            })
        ranked_results.sort(key=lambda x: x["match_score"], reverse=True)
        return ranked_results[:request.top_k]