from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from backend.models.schemas import NotificationSchema
from backend.services.email_service import EmailSenderStub

router = APIRouter()


class TriggerRequest(BaseModel):
    user_id: str


def perform_job_matching(user_id: str) -> List[Dict[str, Any]]:
    """
    دالة محاكاة لوجيك المطابقة
    """
    return [
        {"id": "job_1", "title": "Software Engineer", "company": "Tech Hub"},
        {"id": "job_2", "title": "Data Analyst", "company": "Innovate LLC"}
    ]


@router.post("/trigger-matching")
async def trigger_job_matching(request: TriggerRequest):
    try:
        # 1. تشغيل لوجيك المطابقة
        matched_jobs = perform_job_matching(request.user_id)

        # 2. إنتاج تنبيه حقيقي باستعمال NotificationSchema
        notification = NotificationSchema(
            id=f"notif_{request.user_id}",
            user_id=request.user_id,
            message=f"Found {len(matched_jobs)} new job matches for your profile!",
            status="SENT"
        )

        # 3. إرسال التنبيه عبر الـ Email Stub
        email_sender = EmailSenderStub()
        email_sender.send_email(
            recipient_email="user@example.com",
            subject="New Job Matches Available!",
            body=notification.message
        )

        return {
            "success": True,
            "message": notification.message,
            "jobs": matched_jobs,
            "notification": notification.model_dump() if hasattr(notification, 'model_dump') else notification.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))