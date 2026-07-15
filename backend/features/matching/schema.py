from pydantic import BaseModel
from .model import JobPosting, Profile

class MatchRequest(BaseModel):
    job: JobPosting
    profile: Profile

class MatchResponse(BaseModel):
    match_score: float
    is_match: bool