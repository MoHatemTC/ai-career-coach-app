from pydantic import BaseModel
from backend.models.job_posting import JobPosting
from backend.models.profile import Profile


class MatchRequest(BaseModel):
    job: JobPosting
    profile: Profile


class MatchResponse(BaseModel):
    job_id: str
    match_score: float
    is_match: bool
    explanation: str | None = None