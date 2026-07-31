import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from backend.services.database import get_db
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.models.profile import Profile
from backend.features.matching.scorer import calculate_match_score
from backend.features.matching.retriever import retrieve_top_jobs
from backend.services.matching_pipeline import run_match_pipeline
from pydantic import BaseModel


logger = logging.getLogger(__name__)

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

class PipelineRequest(BaseModel):
    """The UI posts the profile it holds, which is the CV parser's output after
    the user has edited it — a free-form dict, not a validated `Profile`. It is
    typed loosely on purpose: forcing the UI to satisfy `Profile` (user_id,
    experience_years, salary_expectation, ...) would mean inventing values the
    parser never produced.
    """

    profile: Dict[str, Any]
    top_k: Optional[int] = 10


class PipelineResponse(BaseModel):
    ranked: List[Dict[str, Any]]


@router.post("/pipeline", response_model=PipelineResponse)
def run_pipeline(
    request: PipelineRequest, db: Session = Depends(get_db)
) -> PipelineResponse:
    """Retrieve candidate jobs, re-rank them, and explain each one.

    All three stages of the matching chain: Qdrant retrieval, LLM re-ranking,
    then the Match Explanation Agent.

    Retrieval itself reads Qdrant rather than SQL, but the session is needed by
    the explanation stage, which joins each ranked posting back from SQLite on
    `job_id` to recover the skills the Qdrant payload does not carry.
    """
    try:
        ranked = run_match_pipeline(
            request.profile, top_k=request.top_k or 10, session=db
        )
    except Exception as exc:
        # Log the full traceback before converting to HTTPException. FastAPI
        # does not log tracebacks for HTTPException, so without this the server
        # console shows only "503 Service Unavailable" and the actual stage
        # that failed (Qdrant, the embedder, the LLM) is invisible.
        logger.exception("Matching pipeline failed for profile keys=%s",
                         sorted(request.profile.keys()))
        # Surfaced rather than swallowed: a locked or unreachable Qdrant is a
        # real fault, and returning an empty list for it is indistinguishable
        # from "nothing matched".
        raise HTTPException(
            status_code=503,
            detail=f"Matching pipeline failed: {type(exc).__name__}: {exc}",
        ) from exc
    return PipelineResponse(ranked=ranked)
