from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class JobPosting(BaseModel):
    title: str
    company: str
    location: str
    description: str
    skills: List[str]
    salary: Optional[str] = None
    source: str
    url: str
    date: datetime
