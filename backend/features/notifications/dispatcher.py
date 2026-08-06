"""Orchestrates one digest run.

Per user:  top-3 matches -> pick channel -> send -> log.

Two properties this module owns, because nothing downstream can recover them:

* **Isolation** — one user's failure must never abort the run. Every per-user
  step is wrapped; failures are recorded and the loop continues.
* **Idempotency** — a user gets at most one digest per local calendar day, no
  matter how many times the scheduler fires (restart loop, overlapping run,
  someone hitting the manual trigger during a demo).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.features.notifications import settings_service
from backend.features.notifications.matching_bridge import (
    DEFAULT_TOP_N,
    recently_notified_job_ids,
    select_top_matches,
)
from backend.features.notifications.providers import build_provider_chain
from backend.features.notifications.providers.base import NotificationProvider
from backend.features.notifications.schema import (
    DeliveryResult,
    DigestPayload,
    DispatchSummary,
    TopJobMatch,
)
from backend.features.notifications.settings_service import DigestRecipient
from backend.models.db_models import NotificationLogORM

logger = logging.getLogger(__name__)


def local_date_string(
    recipient: DigestRecipient, moment: Optional[datetime] = None
) -> str:
    """The recipient's local calendar date, as YYYY-MM-DD.

    Local, not UTC: a user in UTC+2 whose digest went out at 23:00 local would
    otherwise be eligible again an hour later, on the same day they are living
    in.
    """
    moment = moment or datetime.now(timezone.utc)
    return moment.astimezone(recipient.zone()).strftime("%Y-%m-%d")


def last_sent_at(db: Session, user_id: str) -> Optional[datetime]:
    row = (
        db.query(NotificationLogORM)
        .filter(
            NotificationLogORM.user_id == user_id,
            NotificationLogORM.status == "sent",
        )
        .order_by(NotificationLogORM.created_at.desc())
        .first()
    )
    return row.created_at if row is not None else None


def is_due(
    db: Session, recipient: DigestRecipient, local_date: str
) -> bool:
    """Whether this recipient is owed a digest right now.

    Two separate guards, because they answer different questions:

    * the same-local-day check is *idempotency* — it stops 24 hourly ticks (or
      a restart loop) producing 24 digests;
    * the frequency interval is the user's own *preference* — `weekly` means
      seven days between digests, not seven chances to receive one.
    """
    already_today = (
        db.query(NotificationLogORM)
        .filter(
            NotificationLogORM.user_id == recipient.user_id,
            NotificationLogORM.sent_on_local_date == local_date,
            NotificationLogORM.status == "sent",
        )
        .first()
        is not None
    )
    if already_today:
        return False

    interval = recipient.interval_days()
    if interval <= 1:
        return True

    previous = last_sent_at(db, recipient.user_id)
    if previous is None:
        return True
    # created_at comes back naive from SQLite, written in UTC by the column's
    # server default, so "now" is made naive-UTC to match rather than the row
    # being made aware — the row genuinely carries no offset.
    if previous.tzinfo is not None:
        previous = previous.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now - previous >= timedelta(days=interval)


def _record(
    db: Session,
    recipient: DigestRecipient,
    result: DeliveryResult,
    matches: List[TopJobMatch],
    local_date: str,
) -> None:
    db.add(
        NotificationLogORM(
            user_id=recipient.user_id,
            channel=result.channel,
            provider=result.provider,
            status="sent" if result.success else "failed",
            job_ids=json.dumps([match.job.job_id for match in matches]),
            match_scores=json.dumps([match.match_score for match in matches]),
            provider_message_id=result.message_id,
            error_message=result.error,
            sent_on_local_date=local_date,
        )
    )
    db.commit()


def send_digest_for_user(
    db: Session,
    recipient: DigestRecipient,
    top_n: int = DEFAULT_TOP_N,
    force: bool = False,
    dry_run: bool = False,
    suppress_recent: bool = True,
) -> Tuple[str, List[DeliveryResult]]:
    """Send one recipient's digest.

    Returns `(outcome, results)` where outcome is one of:
    "notified" | "no_contact" | "no_profile" | "already_sent" | "no_matches" |
    "no_new_matches" | "all_failed".

    `suppress_recent` is the 7-day de-duplication (PRD 7.9). It is right for a
    scheduled digest — nobody wants the same three jobs on Tuesday that they
    got on Monday — and wrong for the "send test" button, which exists to put a
    real message through and cannot do that once the only qualifying jobs have
    been sent once. Same reasoning as `force` skipping the daily guard: a person
    testing their own setup should not be refused by a rule meant to protect
    them from repetition.
    """
    local_date = local_date_string(recipient)

    if not recipient.is_reachable():
        return "no_contact", []

    # Reported separately from "no_matches" on purpose. Both end in nothing
    # being sent, but the fix is completely different — one needs a CV, the
    # other needs a lower threshold — and collapsing them sends whoever is
    # debugging a digest to tune a slider that was never the problem.
    if not recipient.profile:
        return "no_profile", []

    if not force and not is_due(db, recipient, local_date):
        return "already_sent", []

    selection = select_top_matches(
        db,
        recipient,
        top_n=top_n,
        exclude_job_ids=(
            recently_notified_job_ids(db, recipient.user_id)
            if suppress_recent
            else set()
        ),
    )
    matches = selection.matches
    if not matches:
        # Deliberately no "we found nothing today" message. A daily email that
        # says nothing useful is how a digest gets muted or marked as spam.
        #
        # The two empty cases are reported separately because their fixes are
        # opposite. "Nothing was good enough" is answered by a lower threshold
        # or more postings; "everything good enough was already sent" is not
        # answered by either, and telling someone to lower a threshold their
        # jobs already cleared sends them to fix the wrong thing.
        if selection.suppressed_as_recent:
            return "no_new_matches", []
        return "no_matches", []

    payload = DigestPayload(
        user_id=recipient.user_id,
        full_name=recipient.full_name,
        matches=matches,
        generated_at=datetime.now(timezone.utc),
    )

    if dry_run:
        return "notified", [DeliveryResult.ok("dry-run", "dry-run", "dry-run-no-send")]

    results: List[DeliveryResult] = []
    for provider in build_provider_chain():
        address = recipient.address_for(provider.channel)
        if address is None:
            continue

        if not provider.is_configured():
            logger.info(
                "Provider %s not configured; trying next channel for %s",
                provider.name,
                recipient.user_id,
            )
            continue

        try:
            result = provider.send(payload, address)
        except Exception as exc:
            # Providers are contracted not to raise, but a bug in one must
            # still not take down the run.
            logger.exception(
                "Provider %s raised for %s", provider.name, recipient.user_id
            )
            result = DeliveryResult.failed(provider.channel, provider.name, str(exc))

        results.append(result)
        _record(db, recipient, result, matches, local_date)

        if result.success:
            # Stop at the first success — this is a fallback chain, not a
            # fan-out. One digest per user, not one per configured channel.
            return "notified", results

    return "all_failed", results


def _is_send_hour(recipient: DigestRecipient) -> bool:
    local_hour = datetime.now(timezone.utc).astimezone(recipient.zone()).hour
    return local_hour == recipient.send_hour_local


def run_daily_dispatch(
    db: Session,
    top_n: int = DEFAULT_TOP_N,
    force: bool = False,
    dry_run: bool = False,
    only_user_id: Optional[str] = None,
    respect_send_hour: bool = True,
) -> DispatchSummary:
    """Run the digest across every reachable user."""
    started = datetime.now(timezone.utc)
    summary = DispatchSummary(run_started_at=started, run_finished_at=started)

    if only_user_id:
        recipient = settings_service.get_recipient(db, only_user_id)
        recipients = [recipient] if recipient else []
    else:
        recipients = settings_service.list_recipients(db)

    for recipient in recipients:
        # The scheduler ticks hourly so users in different timezones get their
        # digest at their own local hour, not everyone at once. Checked before
        # the counter so a user who is simply not due yet is not reported as
        # "considered and skipped".
        if respect_send_hour and not only_user_id and not _is_send_hour(recipient):
            continue

        summary.users_considered += 1
        try:
            outcome, results = send_digest_for_user(
                db, recipient, top_n=top_n, force=force, dry_run=dry_run
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
            elif outcome == "no_new_matches":
                summary.users_skipped_no_new_matches += 1
            elif outcome == "no_profile":
                summary.users_skipped_no_profile += 1
            else:
                summary.errors.append(f"{recipient.user_id}: every channel failed")

        except Exception as exc:
            logger.exception("Dispatch failed for user %s", recipient.user_id)
            summary.errors.append(f"{recipient.user_id}: {exc}")
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
