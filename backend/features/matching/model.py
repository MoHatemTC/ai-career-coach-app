from pydantic import BaseModel
from typing import List


class JobPosting(BaseModel):
    job_id: str
    title: str
    required_skills: List[str]
    min_experience: int
    description: str
    location: str
    work_type: str
    salary: int


class Profile(BaseModel):
    user_id: str
    current_title: str
    skills: List[str]
    experience_years: int
    summary: str
    location: str
    preferred_work_type: str
    salary_expectation: int 