"""Orchestrates one digest run.

Per user:  top-3 matches -> pick channel -> send -> log.

Two properties this module is responsible for, because nothing downstream can
recover them:

* **Isolation** — one user's failure must never abort the run. Every per-user
  step is wrapped; failures are recorded and the loop continues.
* **Idempotency** — a user gets at most one digest per local calendar day per
  channel, no matter how many times the scheduler fires (restart loop,
  overlapping run, someone hitting the manual trigger during a demo).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.features.notifications import settings_service
from backend.features.notifications.matching_bridge import (
    DEFAULT_TOP_N,
    get_top_matches,
    recently_notified_job_ids,
)
from backend.features.notifications.providers import build_provider_chain
from backend.features.notifications.providers.base import NotificationProvider
from backend.features.notifications.schema import (
    DeliveryResult,
    DigestPayload,
    DispatchSummary,
    TopJobMatch,
)
from backend.models.db_models import NotificationLogORM
from backend.models.user import UserRead

logger = logging.getLogger(__name__)


def local_date_string(user: UserRead, moment: Optional[datetime] = None) -> str:
    """The user's local calendar date, as YYYY-MM-DD."""
    moment = moment or datetime.now(timezone.utc)
    try:
        local = moment.astimezone(ZoneInfo(user.settings.timezone))
    except Exception:
        # Timezone is validated on write, but a row could predate that
        # validation. Falling back to UTC is better than skipping the user.
        logger.warning(
            "User %s has unusable timezone %r; falling back to UTC",
            user.user_id,
            user.settings.timezone,
        )
        local = moment.astimezone(timezone.utc)
    return local.strftime("%Y-%m-%d")


def already_sent_today(db: Session, user: UserRead, local_date: str) -> bool:
    return (
        db.query(NotificationLogORM)
        .filter(
            NotificationLogORM.user_id == user.user_id,
            NotificationLogORM.sent_on_local_date == local_date,
            NotificationLogORM.status == "sent",
        )
        .first()
        is not None
    )


def _recipient_for(provider: NotificationProvider, user: UserRead) -> Optional[str]:
    """The address to use, or None if this channel is off / unset for the user."""
    if provider.channel == "whatsapp":
        if user.settings.notify_via_whatsapp and user.settings.phone:
            return user.settings.phone
        return None
    if provider.channel == "email":
        if user.settings.notify_via_email and user.settings.email:
            return user.settings.email
        return None
    return None


def _record(
    db: Session,
    user: UserRead,
    result: DeliveryResult,
    matches: List[TopJobMatch],
    local_date: str,
) -> None:
    db.add(
        NotificationLogORM(
            user_id=user.user_id,
            channel=result.channel,
            provider=result.provider,
            status="sent" if result.success else "failed",
            job_ids=[match.job.job_id for match in matches],
            match_scores=[match.match_score for match in matches],
            provider_message_id=result.message_id,
            error_message=result.error,
            sent_on_local_date=local_date,
        )
    )
    db.commit()


def send_digest_for_user(
    db: Session,
    user: UserRead,
    top_n: int = DEFAULT_TOP_N,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[str, List[DeliveryResult]]:
    """Send one user's digest.

    Returns `(outcome, results)` where outcome is one of:
    "notified" | "no_contact" | "already_sent" | "no_matches" | "all_failed".
    """
    app_base_url = os.getenv("APP_BASE_URL", "")
    local_date = local_date_string(user)

    if not user.is_reachable():
        return "no_contact", []

    if not force and already_sent_today(db, user, local_date):
        return "already_sent", []

    matches = get_top_matches(
        db,
        user,
        top_n=top_n,
        exclude_job_ids=recently_notified_job_ids(db, user.user_id),
        app_base_url=app_base_url,
    )
    if not matches:
        # Deliberately no "we found nothing" message. A daily email that says
        # nothing useful is how a digest gets muted or marked as spam.
        return "no_matches", []

    payload = DigestPayload(
        user_id=user.user_id,
        full_name=user.full_name,
        matches=matches,
        generated_at=datetime.now(timezone.utc),
    )

    if dry_run:
        return "notified", [
            DeliveryResult.ok("dry-run", "dry-run", "dry-run-no-send")
        ]

    results: List[DeliveryResult] = []
    for provider in build_provider_chain():
        recipient = _recipient_for(provider, user)
        if recipient is None:
            continue

        if not provider.is_configured():
            logger.info(
                "Provider %s not configured; trying next channel for %s",
                provider.name,
                user.user_id,
            )
            continue

        try:
            result = provider.send(payload, recipient)
        except Exception as exc:
            # Providers are contracted not to raise, but a bug in one must
            # still not take down the run.
            logger.exception("Provider %s raised for %s", provider.name, user.user_id)
            result = DeliveryResult.failed(provider.channel, provider.name, str(exc))

        results.append(result)
        _record(db, user, result, matches, local_date)

        if result.success:
            # Stop at the first success — this is the fallback, not a fan-out.
            return "notified", results

    return "all_failed", results


def run_daily_dispatch(
    db: Session,
    top_n: int = DEFAULT_TOP_N,
    force: bool = False,
    dry_run: bool = False,
    only_user_id: Optional[str] = None,
    respect_send_hour: bool = True,
) -> DispatchSummary:
    """Run the digest across all notifiable users."""
    started = datetime.now(timezone.utc)
    summary = DispatchSummary(run_started_at=started, run_finished_at=started)

    if only_user_id:
        user = settings_service.get_user(db, only_user_id)
        users = [user] if user else []
    else:
        users = settings_service.list_notifiable_users(db)

    for user in users:
        summary.users_considered += 1
        try:
            # The scheduler ticks hourly so users in different timezones get
            # their digest at their own local send_hour, not everyone at once.
            if respect_send_hour and not only_user_id:
                local_hour = datetime.now(timezone.utc).astimezone(
                    ZoneInfo(user.settings.timezone)
                ).hour
                if local_hour != user.settings.send_hour_local:
                    summary.users_considered -= 1
                    continue

            outcome, results = send_digest_for_user(
                db, user, top_n=top_n, force=force, dry_run=dry_run
            )
            summary.deliveries.extend(results)

            if outcome == "notified":
                summary.users_notified += 1
            elif outcome == "no_contact":
                summary.users_skipped_no_contact += 1
            elif outcome == "already_sent":
                summary.users_skipped_already_sent += 1
            elif outcome == "no_matches":
                summary.users_skipped_no_matches += 1
            else:
                summary.errors.append(f"{user.user_id}: every channel failed")

        except Exception as exc:
            logger.exception("Dispatch failed for user %s", user.user_id)
            summary.errors.append(f"{user.user_id}: {exc}")
            db.rollback()

    summary.run_finished_at = datetime.now(timezone.utc)
    logger.info(
        "Digest run finished in %.1fs: %s/%s notified, %s errors",
        summary.duration_seconds,
        summary.users_notified,
        summary.users_considered,
        len(summary.errors),
    )
    return summary
