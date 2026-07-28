from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from backend.models.schemas import NotificationSchema
from backend.services.email_service import EmailSenderStub

# --- 1. (جديد) استدعاء دالة الـ Pipeline من ملف الـ scheduler ---
from backend.scheduler import trigger_pipeline_now

router = APIRouter()


class TriggerRequest(BaseModel):
    user_id: str
    profile_data: Optional[Dict[str, Any]] = None  # لتمكين إرسال بيانات البروفايل اختياريًا


def perform_job_matching(user_id: str, profile_data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    تشغيل الـ Pipeline الحقيقي (Menna -> Ramez -> Mohamed Farag) 
    بدلاً من البيانات الثابتة القديمة
    """
    user_profile = profile_data or {"user_id": user_id}
    
    # استدعاء السلسلة بالترتيب من ملف scheduler
    pipeline_output = trigger_pipeline_now(user_profile)
    
    # إرجاع مخرجات فرج النهائية (الوظائف + نقاط القوة والضعف)
    return pipeline_output.get("results", [])


@router.post("/trigger-matching")
@router.post("/trigger-now")  # إضافة مسار إضافي لدعم كلا التسميتين من الفراننت إند
async def trigger_job_matching(request: TriggerRequest):
    try:
        # 1. تشغيل لوجيك المطابقة الحقيقي عبر الـ Pipeline
        matched_jobs = perform_job_matching(request.user_id, request.profile_data)

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