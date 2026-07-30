from pydantic import BaseModel, EmailStr
from typing import List, Optional


class ProfileBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None

    skills: Optional[List[str]] = None
    education: Optional[List[str]] = None
    experience: Optional[List[str]] = None


class ProfileUpdate(ProfileBase):
    pass