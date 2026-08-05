import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import (
    TEST_MODE,
    TEST_INTERVAL_MINUTES,
    NOTIFICATION_TIME,
)

from backend.services.database import SessionLocal
from backend.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def notification_job():
    """
    Main scheduled notification task.
    Runs periodically and delegates the work to NotificationService.
    """

    logger.info("Notification scheduler triggered.")

    db = SessionLocal()

    try:
        logger.info("Running notification workflow...")

        service = NotificationService()
        service.notify_all_users(db)

    except Exception:
        logger.exception("Notification scheduler failed.")

    finally:
        db.close()


def start_scheduler():
    """
    Start the notification scheduler.
    """

    if scheduler.running:
        return

    if TEST_MODE:

        scheduler.add_job(
            notification_job,
            IntervalTrigger(minutes=TEST_INTERVAL_MINUTES),
            id="notification_job",
            replace_existing=True,
        )

        logger.info(
            "Notification scheduler started in TEST mode "
            "(every %s minutes).",
            TEST_INTERVAL_MINUTES,
        )

    else:

        hour, minute = map(int, NOTIFICATION_TIME.split(":"))

        scheduler.add_job(
            notification_job,
            CronTrigger(hour=hour, minute=minute),
            id="notification_job",
            replace_existing=True,
        )

        logger.info(
            "Notification scheduler started in PRODUCTION mode "
            "(daily at %s).",
            NOTIFICATION_TIME,
        )

    scheduler.start()


def stop_scheduler():
    """
    Stop the notification scheduler.
    """

    if scheduler.running:
        scheduler.shutdown()
        logger.info("Notification scheduler stopped.")