import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.models.schemas import JobSchema, ProfileSchema, NotificationSchema
from backend.services.email_service import EmailSenderStub

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)


def daily_noop_job():
    logger.info("[Scheduler] Daily no-op job executed successfully! Scheduler is active and ticking.")


def daily_matching_job():
    """
    الوظيفة اليومية المسؤولة عن المطابقة وإرسال التنبيهات أوتوماتيكياً
    """
    logger.info("[Scheduler] Starting Daily Job Matching process...")
    
    # 1. تشغيل لوجيك المطابقة (محاكاة لمستخدم)
    test_user_id = "user_1"
    matched_jobs = [
        {"id": "job_1", "title": "Software Engineer", "company": "Tech Hub"},
        {"id": "job_2", "title": "Data Analyst", "company": "Innovate LLC"}
    ]
    
    # 2. إنشاء كائن التنبيه من الـ Schema
    notification = NotificationSchema(
        id=f"sched_notif_{test_user_id}",
        user_id=test_user_id,
        message=f"[Daily Automation] Found {len(matched_jobs)} job matches for you today!",
        status="SENT"
    )
    
    # 3. إرسال التنبيه بواسطة EmailSenderStub
    email_sender = EmailSenderStub()
    email_sender.send_email(
        recipient_email="user@example.com",
        subject="Daily Job Matches Digest",
        body=notification.message
    )
    
    logger.info(f"[Scheduler] ✓ Daily Job Matching completed. Notification sent: {notification.message}")


def start_scheduler():
    scheduler = BlockingScheduler()
    
    scheduler.add_job(
        daily_noop_job, 
        trigger='interval', 
        days=1, 
        id='daily_noop_job_id',
        next_run_time=datetime.now() 
    )
    
    scheduler.add_job(
        daily_matching_job,
        trigger='cron',
        hour=0,
        minute=0,
        id='daily_matching_job_id'
    )
    
    logger.info("[Scheduler] Starting scheduler... Daily jobs registered.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Scheduler] Scheduler stopped manually.")


if __name__ == "__main__":
    logger.info("--- Starting Automation Foundation Backend ---")
    
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

    email_sender = EmailSenderStub()
    email_sender.send_email(
        recipient_email=test_profile.email,
        subject="Sprint 1 Test Email",
        body=f"Hello {test_profile.name}, your setup is ready!"
    )

    start_scheduler()