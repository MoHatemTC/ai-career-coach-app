"""HTTP surface for previewing, sending, and diagnosing the digest.

Mounted under `/notifications` alongside `backend/routes/notifications.py`,
which keeps the Contract 6 settings endpoints. Two routers share the prefix on
purpose: the settings contract is read by another lane and should not move, and
"where contact details are stored" is a genuinely different concern from "how a
message gets sent".

Paths here never begin with `settings`, so nothing collides.

Handlers stay thin per CONTRIBUTING — the logic lives in settings_service /
matching_bridge / dispatcher.

Every route that sends a message, or reads data belonging to a named user, is
behind `authz.require_admin_token`. Read that module before changing anything
here: the gate is a shared secret standing in for the per-user auth this
service does not have yet, and which routes it covers is a deliberate list
rather than a default.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.features.notifications import settings_service
from backend.features.notifications.authz import require_admin_token
from backend.features.notifications.dispatcher import (
    run_daily_dispatch,
    send_digest_for_user,
)
from backend.features.notifications.matching_bridge import (
    DEFAULT_TOP_N,
    get_top_matches,
    recently_notified_job_ids,
)
from backend.features.notifications.providers import build_provider_chain
from backend.features.notifications.scheduler import get_scheduler_status
from backend.features.notifications.schema import DispatchSummary, TopJobMatch
from backend.models.db_models import NotificationLogORM
from backend.services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class ProviderStatus(BaseModel):
    channel: str
    name: str
    configured: bool
    #: False when the channel will run but not actually transmit — today that
    #: means SMTP in console mode. `configured` alone said "yes" for a channel
    #: that prints to a log, which reads as working delivery.
    delivers: bool = True
    note: Optional[str] = None


class NotificationLogOut(BaseModel):
    id: int
    user_id: str
    channel: str
    provider: Optional[str] = None
    status: str
    job_ids: List[str] = []
    error_message: Optional[str] = None
    sent_on_local_date: str


class SendResult(BaseModel):
    outcome: str
    results: List[Dict[str, Any]] = []


class ProfileSnapshotIn(BaseModel):
    """The profile the digest scores against.

    Loosely typed on purpose, exactly as `PipelineRequest` in the matching
    routes is: this is the CV parser's output after the user has edited it, and
    forcing it through a strict model would mean inventing values the parser
    never produced.
    """

    profile: Dict[str, Any]


# --- Profile snapshot -------------------------------------------------------


@router.put("/settings/{user_id}/profile", dependencies=[Depends(require_admin_token)])
def save_profile_snapshot(
    user_id: str, payload: ProfileSnapshotIn, db: Session = Depends(get_db)
):
    """Store the matching inputs the scheduled digest will score against.

    Called by the frontend once a CV has been parsed. Without it the digest can
    only run for a user who happens to have a browser tab open, which is the
    opposite of what an unprompted daily notification is for.

    404 means no settings row exists yet — save contact details first. The
    profile is stored *on* the settings row rather than in its own table
    because it is the same single-user demo key, and a second table would need
    the same migration when auth lands.
    """
    recipient = settings_service.save_profile_snapshot(db, user_id, payload.profile)
    if recipient is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No notification settings for user {user_id!r}. "
                "Save contact details before attaching a profile."
            ),
        )
    return {
        "user_id": recipient.user_id,
        "full_name": recipient.full_name,
        "profile_fields": sorted(recipient.profile.keys()),
    }


# --- Preview & dispatch -----------------------------------------------------


@router.get(
    "/preview/{user_id}",
    response_model=List[TopJobMatch],
    dependencies=[Depends(require_admin_token)],
)
def preview_digest(
    user_id: str,
    top_n: int = Query(DEFAULT_TOP_N, ge=1, le=10),
    include_recent: bool = Query(
        False, description="Include jobs already sent in the last 7 days."
    ),
    db: Session = Depends(get_db),
):
    """Exactly what the next digest would contain — without sending anything.

    This is what the settings page renders, so the preview and the message are
    produced by the same code rather than by two implementations that can
    drift.
    """
    recipient = settings_service.get_recipient(db, user_id)
    if recipient is None:
        raise HTTPException(
            status_code=404, detail=f"No notification settings for user {user_id!r}."
        )

    exclude = set() if include_recent else recently_notified_job_ids(db, user_id)
    return get_top_matches(db, recipient, top_n=top_n, exclude_job_ids=exclude)


@router.post(
    "/send-test/{user_id}",
    response_model=SendResult,
    dependencies=[Depends(require_admin_token)],
)
def send_test_digest(
    user_id: str,
    dry_run: bool = Query(
        False, description="Render and pick a channel, but do not transmit."
    ),
    db: Session = Depends(get_db),
):
    """Send this user's digest right now, bypassing the once-per-day guard.

    `force=True` so someone testing their own setup is not told "already sent
    today" — which is the single most confusing thing a test button can say.
    """
    recipient = settings_service.get_recipient(db, user_id)
    if recipient is None:
        raise HTTPException(
            status_code=404, detail=f"No notification settings for user {user_id!r}."
        )

    # `suppress_recent=False`: the de-dupe window exists so a *scheduled*
    # digest does not repeat itself. Applied to a test send it guarantees the
    # button stops working the moment it has worked once, which is the exact
    # opposite of what it is for.
    outcome, results = send_digest_for_user(
        db, recipient, force=True, dry_run=dry_run, suppress_recent=False
    )
    return SendResult(
        outcome=outcome, results=[result.model_dump() for result in results]
    )


@router.post(
    "/dispatch",
    response_model=DispatchSummary,
    dependencies=[Depends(require_admin_token)],
)
def trigger_dispatch(
    dry_run: bool = Query(False),
    force: bool = Query(False, description="Ignore the once-per-day guard."),
    respect_send_hour: bool = Query(
        False,
        description=(
            "Only send to users whose local send hour is now. The scheduler "
            "sets this True; manual runs default False."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Run the whole digest on demand — for the demo, and for debugging.

    The most dangerous route in this feature: it reaches every user on record.
    `require_admin_token` is what stands in front of it, and in any deployment
    that can actually send, that means `NOTIFICATIONS_ADMIN_TOKEN` must be set
    or this returns 503. See authz.py and docs/notifications.md.
    """
    return run_daily_dispatch(
        db, force=force, dry_run=dry_run, respect_send_hour=respect_send_hour
    )


# --- Diagnostics ------------------------------------------------------------


@router.get("/scheduler")
def scheduler_status() -> dict:
    return get_scheduler_status()


@router.get("/providers", response_model=List[ProviderStatus])
def provider_status():
    """Which channels are actually usable right now.

    The first thing to check when a digest does not arrive.
    """
    statuses = []
    for provider in build_provider_chain():
        console = bool(getattr(provider, "is_console", False))
        statuses.append(
            ProviderStatus(
                channel=provider.channel,
                name="console" if console else provider.name,
                configured=provider.is_configured(),
                delivers=provider.is_configured() and not console,
                note=(
                    "EMAIL_HOST is unset, so digests print to the API console "
                    "instead of being sent. Set the EMAIL_* variables in .env "
                    "to deliver for real."
                    if console
                    else None
                ),
            )
        )
    return statuses


@router.get(
    "/logs",
    response_model=List[NotificationLogOut],
    dependencies=[Depends(require_admin_token)],
)
def recent_logs(
    user_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Recent delivery attempts, newest first. Failures included — they are the
    ones worth reading."""
    query = db.query(NotificationLogORM)
    if user_id:
        query = query.filter(NotificationLogORM.user_id == user_id)

    # `id` breaks the tie: created_at has one-second resolution in SQLite, and
    # the rows most worth reading together — a WhatsApp failure and the email
    # success that followed it — are written inside the same second.
    rows = (
        query.order_by(
            NotificationLogORM.created_at.desc(), NotificationLogORM.id.desc()
        )
        .limit(limit)
        .all()
    )

    out = []
    for row in rows:
        try:
            job_ids = json.loads(row.job_ids or "[]")
        except (json.JSONDecodeError, TypeError):
            job_ids = []
        out.append(
            NotificationLogOut(
                id=row.id,
                user_id=row.user_id,
                channel=row.channel,
                provider=row.provider,
                status=row.status,
                job_ids=[str(job_id) for job_id in job_ids],
                error_message=row.error_message,
                sent_on_local_date=row.sent_on_local_date,
            )
        )
    return out
