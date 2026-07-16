from fastapi import APIRouter
from backend.models.job_posting import JobPosting
from backend.models.profile import Profile
from .schema import MatchRequest, MatchResponse
from .scorer import calculate_match

router = APIRouter()

@router.post("/match", response_model=MatchResponse)
def get_match(request: MatchRequest):
    return calculate_match(request.job, request.profile)