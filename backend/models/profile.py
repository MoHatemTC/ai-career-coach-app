from pydantic import BaseModel
from typing import List

class Profile(BaseModel):
    user_id: str
    current_title: str
    skills: List[str]
    experience_years: int
    summary: str
    location: str
    preferred_work_type: str
    salary_expectation: int