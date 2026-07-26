from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pgvector.sqlalchemy import CosineDistance

from backend.services.database import get_db
from backend.features.matching.scorer import get_model
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.features.matching.schema import MatchRequest 

router = APIRouter(prefix="/matching", tags=["Matching"])

@router.post("/rank-jobs")
def rank_jobs(request: MatchRequest, db: Session = Depends(get_db)):
    model = get_model()
    profile_text = f"{request.profile.skills} {request.profile.bio}"
    profile_embedding = model.encode(profile_text).tolist()
    
   
    db_jobs = (
        db.query(JobPostingORM)
        .order_by(JobPostingORM.embedding.cosine_distance(profile_embedding))
        .limit(50)
        .all()
    )
    
    return [orm_to_job_posting(job) for job in db_jobs]