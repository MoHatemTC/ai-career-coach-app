"""Daily scheduling engine (APScheduler).

PRD 10.1 names "a scheduler (cron / APScheduler)". APScheduler is chosen over
cron because it runs in-process with the FastAPI app — one thing to deploy,
and it works identically on the Windows machines the team develops on, where
cron does not exist.

Why the job ticks **hourly** rather than once a day
---------------------------------------------------
Each user picks their own `send_hour_local` in their own `timezone`. A single
daily fire would deliver to everyone at the same instant, which is the wrong
local time for anyone outside the server's timezone. So the trigger runs at
the top of every hour and `run_daily_dispatch()` only sends to users whose
local hour matches theirs right now. The per-user, per-local-day idempotency
check in the dispatcher is what keeps 24 ticks from producing 24 digests.

Scaling note: this is a single-process, in-memory scheduler. If the API is
ever run with more than one worker (`uvicorn --workers 2`), every worker gets
its own scheduler and the job fires N times. The dispatcher's idempotency
check makes that safe rather than catastrophic, but the correct fix is to run
the scheduler as its own single-replica process — see `scripts/run_scheduler.py`.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.features.notifications.dispatcher import run_daily_dispatch
from backend.services.database import SessionLocal

logger = logging.getLogger(__name__)

JOB_ID = "daily_top_job_matches"

_scheduler: Optional[BackgroundScheduler] = None


def scheduler_enabled() -> bool:
    """Off unless explicitly enabled.

    Default-off matters: without it, every developer running the API locally
    and every CI job that imports `backend.main` would start firing real
    notifications at real phone numbers.
    """
    return os.getenv("NOTIFICATIONS_SCHEDULER_ENABLED", "false").lower() == "true"


def _tick() -> None:
    """One scheduler fire. Owns its own DB session.

    The request-scoped `get_db()` dependency is unavailable here — this runs
    on a background thread with no request — so the session is opened and
    closed explicitly.
    """
    db = SessionLocal()
    try:
        summary = run_daily_dispatch(db)
        if summary.users_considered:
            logger.info(
                "Scheduled digest: considered=%s notified=%s errors=%s",
                summary.users_considered,
                summary.users_notified,
                len(summary.errors),
            )
    except Exception:
        # Never let an exception escape into APScheduler's thread — it would
        # kill the job and stop all future runs silently.
        logger.exception("Scheduled digest run failed")
    finally:
        db.close()


def start_scheduler() -> Optional[BackgroundScheduler]:
    global _scheduler

    if not scheduler_enabled():
        logger.info(
            "Notification scheduler disabled "
            "(set NOTIFICATIONS_SCHEDULER_ENABLED=true to turn it on)"
        )
        return None

    if _scheduler and _scheduler.running:
        return _scheduler

    minute = int(os.getenv("NOTIFICATIONS_TICK_MINUTE", "0"))

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _tick,
        trigger=CronTrigger(minute=minute, timezone="UTC"),
        id=JOB_ID,
        name="Daily top-3 job match digest",
        # If the app was down when a tick was due, run it once on startup
        # rather than replaying every missed hour.
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Notification scheduler started (hourly at minute %s UTC)", minute)
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        # wait=False: a shutdown should not block on an in-flight digest run.
        _scheduler.shutdown(wait=False)
        logger.info("Notification scheduler stopped")
    _scheduler = None


def get_scheduler_status() -> dict:
    """Introspection for the /notifications/scheduler endpoint and the UI."""
    if not _scheduler or not _scheduler.running:
        return {"running": False, "enabled": scheduler_enabled(), "next_run_at": None}

    job = _scheduler.get_job(JOB_ID)
    return {
        "running": True,
        "enabled": True,
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }
