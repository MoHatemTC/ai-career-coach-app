from backend.models.job_posting import JobPosting
from backend.models.profile import Profile
from .schema import MatchResponse

def calculate_match(job: JobPosting, profile: Profile) -> MatchResponse:
    job_skills = {skill.strip().lower() for skill in job.required_skills}
    user_skills = {skill.strip().lower() for skill in profile.skills}
    shared_skills = job_skills.intersection(user_skills)

    if len(job_skills) == 0:
        score = 0.0
    else:
        score = (len(shared_skills) / len(job_skills)) * 100

    return MatchResponse(
        job_id=job.job_id,
        match_score=round(score, 2),
        is_match=score >= 50.0,
        explanation="Matched based on required skills."
    )