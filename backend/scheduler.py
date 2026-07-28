import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.models.schemas import JobSchema, ProfileSchema, NotificationSchema
from backend.services.email_service import EmailSenderStub

# --- (جديد) استدعاء دوال زمايلك في التيم لربط الـ Pipeline ---
try:
    from backend.services.ingestion import retrieve_top_10_jobs                   # دالة منة
    from backend.services.llm_service import rank_top_3_jobs, generate_fit_explanation  # دوال رامز وفرج
except ImportError:
    # احتياطي في حال عدم اكتمل استدعاء الدوال من الملفات الأخرى
    retrieve_top_10_jobs = None
    rank_top_3_jobs = None
    generate_fit_explanation = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)


# =====================================================================
# 🚀 (جديد) الدالة المطلوبة لتاسك الأسبوع ده (Trigger Now Functionality)
# =====================================================================
def trigger_pipeline_now(user_profile: dict = None) -> dict:
    """
    الدالة المسؤولة عن تشغيل السلسلة عند الضغط على زر Trigger Now:
    Menna (Top 10) -> Ramez (Top 3) -> Mohamed Farag (Fit Explanation)
    """
    logger.info("[Pipeline] 🚀 Starting Trigger Now pipeline execution...")

    # في حالة عدم وجود بروفايل مبعوث، نستخدم بروفايل تجريبي للاختبار
    if not user_profile:
        user_profile = {
            "user_id": "user_1",
            "full_name": "Omar",
            "skills": ["Python", "SQL", "FastAPI"],
            "target_roles": ["Backend Developer"]
        }

    try:
        # 1. Menna: جلب أعلى 10 وظائف
        logger.info("[Pipeline] Step 1: Retrieving top 10 jobs (Menna)...")
        if callable(retrieve_top_10_jobs):
            top_10_jobs = retrieve_top_10_jobs(user_profile)
        else:
            top_10_jobs = [{"job_id": f"job_{i}", "title": f"Job {i}"} for i in range(1, 11)]

        # 2. Ramez: فلترة الوظائف لأفضل 3 بالذكاء الاصطناعي
        logger.info("[Pipeline] Step 2: Re-ranking top 3 jobs via LLM (Ramez)...")
        if callable(rank_top_3_jobs):
            top_3_jobs = rank_top_3_jobs(user_profile, top_10_jobs)
        else:
            top_3_jobs = top_10_jobs[:3]

        # 3. Mohamed Farag: كتابة نقاط القوة والضعف والتوصية
        logger.info("[Pipeline] Step 3: Generating strength & weakness feedback (Mohamed Farag)...")
        if callable(generate_fit_explanation):
            final_feedback = generate_fit_explanation(user_profile, top_3_jobs)
        else:
            final_feedback = [
                {
                    "job_id": job.get("job_id", "job_1"),
                    "title": job.get("title", "Software Engineer"),
                    "strength": "Strong match on technical skills",
                    "weakness": "Needs more experience in cloud deployment",
                    "recommendation": "Take a short Docker/AWS course"
                } for job in top_3_jobs
            ]

        logger.info("[Pipeline] ✅ Pipeline execution completed successfully.")
        return {
            "status": "success",
            "user_id": user_profile.get("user_id", "user_1"),
            "results": final_feedback
        }

    except Exception as e:
        logger.error(f"[Pipeline] ❌ Error during pipeline execution: {e}")
        raise e


def daily_noop_job():
    logger.info("[Scheduler] Daily no-op job executed successfully! Scheduler is active and ticking.")


def daily_matching_job():
    """
    الوظيفة اليومية المسؤولة عن المطابقة وإرسال التنبيهات أوتوماتيكياً
    """
    logger.info("[Scheduler] Starting Daily Job Matching process...")
    
    # 1. تشغيل الـ Pipeline الكامل
    pipeline_data = trigger_pipeline_now()
    matched_jobs = pipeline_data.get("results", [])
    
    test_user_id = "user_1"
    
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