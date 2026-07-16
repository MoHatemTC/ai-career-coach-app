# backend/scheduler.py
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

# استيراد الـ Schemas والخدمات التي قمنا بإنشائها
from backend.models.schemas import JobSchema, ProfileSchema, ApplicationSchema, ApplicationStatus
from backend.services.email_service import EmailSenderStub

# إعداد الـ Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)


def daily_noop_job():
    """
    الوظيفة اليومية الـ 'No-op' للـ Scheduler
    """
    logger.info("[Scheduler] Daily no-op job executed successfully! Scheduler is active and ticking.")


def start_scheduler():
    scheduler = BlockingScheduler()
    
    # إضافة الـ Job لتعمل يومياً (وتبدأ فوراً عند التشغيل للتجربة)
    scheduler.add_job(
        daily_noop_job, 
        trigger='interval', 
        days=1, 
        id='daily_noop_job_id',
        next_run_time=datetime.now() 
    )
    
    logger.info("[Scheduler] Starting scheduler... Daily job registered.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Scheduler] Scheduler stopped manually.")


if __name__ == "__main__":
    logger.info("--- Starting Automation Foundation Backend ---")
    
    # 1. اختبار صحة الموديلات (Validation Test)
    try:
        test_job = JobSchema(
            id="job_99",
            title="AI Engineer",
            description="Build cool LLM agents",
            location="Remote",
            work_type="Full-time",
            salary=30000.0
        )
        test_profile = ProfileSchema(
            id="prof_01",
            user_id="user_1",
            name="Omar",
            email="omar@example.com",
            location="Giza",
            salary_expectation=28000.0
        )
        logger.info("✓ Models and Schemas loaded and verified successfully!")
    except Exception as e:
        logger.error(f"✗ Schema validation failed: {e}")
        exit(1)

    # 2. تجربة الـ Email Sender Stub
    email_sender = EmailSenderStub()
    email_sender.send_email(
        recipient_email=test_profile.email,
        subject="Sprint 1 Test Email",
        body=f"Hello {test_profile.name}, your setup is ready!"
    )

    # 3. تشغيل الـ Scheduler
    start_scheduler()