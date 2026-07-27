from pydantic import BaseModel
from typing import List, Optional

class JobPosting(BaseModel):
    job_id: str
    title: str
    company: Optional[str] = ""
    required_skills: List[str] = []
    min_experience: int = 0
    description: str = ""
    location: str = ""
    work_type: str = ""
    salary: int = 0