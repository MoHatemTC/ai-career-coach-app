from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pgvector.sqlalchemy import CosineDistance

from backend.services.database import get_db
from backend.features.matching.scorer import get_model
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.features.matching.schema import MatchRequest

router = APIRouter(tags=["Matching"])

@router.post("/rank-jobs")
def rank_jobs(
    request: MatchRequest, 
    limit: int = Query(default=50, ge=1, le=100), 
    db: Session = Depends(get_db)
):
    model = get_model()
    skills_text = " ".join(request.profile.skills) if request.profile.skills else ""
    summary_text = request.profile.summary if request.profile.summary else ""
    profile_text = f"{skills_text} {summary_text}"
    
    profile_embedding = model.encode(profile_text).tolist()
    
    results = (
        db.query(
            JobPostingORM,
            (1 - JobPostingORM.embedding.cosine_distance(profile_embedding)).label("match_score")
        )
        .order_by(JobPostingORM.embedding.cosine_distance(profile_embedding))
        .limit(limit)
        .all()
    )
    
    ranked_jobs = []
    for job_orm, score in results:
        job_data = orm_to_job_posting(job_orm)
        ranked_jobs.append({
            "job": job_data,
            "match_score": float(score)
        })
        
    return ranked_jobs