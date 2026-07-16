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