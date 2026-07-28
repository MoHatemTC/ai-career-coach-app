# backend/models/schemas.py
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, EmailStr

class ApplicationStatus(str, Enum):
    REVIEWED = "reviewed"
    SAVED = "saved"
    APPLIED = "applied"

# الـ Schema الخاصة بالوظيفة
class JobSchema(BaseModel):
    id: str
    title: str
    description: str
    location: str = Field(..., description="مكان الوظيفة (مثال: Cairo, Remote, Hybrid)")
    work_type: str = Field(..., description="نوع العمل (مثال: Full-time, Part-time, Internship)")
    salary: float = Field(..., description="الراتب المعروض للوظيفة")

# الـ Schema الخاصة بملف المستخدم
class ProfileSchema(BaseModel):
    id: str
    user_id: str
    name: str
    email: EmailStr
    location: str = Field(..., description="الموقع الحالي للمرشح")
    salary_expectation: float = Field(..., description="الراتب المتوقع من قبل المرشح")
    cv_url: Optional[str] = None

# الـ Schema الخاصة بحالة التقديم
class ApplicationSchema(BaseModel):
    id: str
    profile_id: str
    job_id: str
    status: ApplicationStatus = ApplicationStatus.SAVED
    applied_at: datetime = Field(default_factory=datetime.utcnow)

# الـ Schema الخاصة بالإشعارات
class NotificationSchema(BaseModel):
    id: str
    user_id: str
    title: str
    content: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False 