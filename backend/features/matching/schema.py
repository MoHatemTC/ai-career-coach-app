from pydantic import BaseModel
from backend.models.profile import Profile

class MatchRequest(BaseModel):
    profile: Profile

class RankedJobResponse(BaseModel):
    job_id: str
    title: str
    company: str
    match_score: float