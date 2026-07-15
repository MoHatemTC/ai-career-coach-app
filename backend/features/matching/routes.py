from fastapi import APIRouter
from .model import JobPosting, Profile 
from .schema import MatchRequest, MatchResponse
from .scorer import calculate_match

router = APIRouter()

@router.post("/match", response_model=MatchResponse)
def get_match(request: MatchRequest):
    return calculate_match(request.job, request.profile)