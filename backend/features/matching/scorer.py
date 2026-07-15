from .model import JobPosting, Profile
from .schema import MatchResponse

def calculate_match(job: JobPosting, profile: Profile) -> MatchResponse:
    job_skills = set(job.required_skills)
    user_skills = set(profile.skills)
    
    shared_skills = job_skills.intersection(user_skills)
    
    if len(job_skills) == 0:
        score = 0.0
    else:
        score = (len(shared_skills) / len(job_skills)) * 100
        
    return MatchResponse(
        match_score=round(score, 2),
        is_match=score >= 50.0 
    )