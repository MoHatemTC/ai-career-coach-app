"""HTTP surface for notification settings, previews, and manual dispatch.

Mounted under /notifications by backend/main.py.

Handlers stay thin per CONTRIBUTING — validation and business logic live in
settings_service / dispatcher / matching_bridge.
"""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.features.notifications import settings_service
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
from backend.models.user import (
    NotificationSettingsUpdate,
    ProfileSnapshot,
    UserCreate,
    UserRead,
)
from backend.services.database import get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationLogOut(BaseModel):
    id: int
    user_id: str
    channel: str
    provider: Optional[str]
    status: str
    job_ids: List[str] = []
    error_message: Optional[str]
    sent_on_local_date: str


class ProviderStatus(BaseModel):
    channel: str
    name: str
    configured: bool


# --- Users & settings ------------------------------------------------------


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_or_replace_user(payload: UserCreate, db: Session = Depends(get_db)):
    return settings_service.upsert_user(db, payload)


@router.get("/users", response_model=List[UserRead])
def list_users(only_enabled: bool = False, db: Session = Depends(get_db)):
    return settings_service.list_users(db, only_enabled=only_enabled)


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = settings_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown user: {user_id}")
    return user


@router.patch("/users/{user_id}/settings", response_model=UserRead)
def update_settings(
    user_id: str,
    patch: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Partial update — this is what the settings tab submits."""
    user = settings_service.update_settings(db, user_id, patch)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown user: {user_id}")
    return user


@router.put("/users/{user_id}/profile", response_model=UserRead)
def update_profile(
    user_id: str,
    profile: ProfileSnapshot,
    db: Session = Depends(get_db),
):
    """Refresh matching inputs. See the CV-lane integration note in settings_service."""
    user = settings_service.update_profile_snapshot(db, user_id, profile)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown user: {user_id}")
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db)):
    if not settings_service.delete_user(db, user_id):
        raise HTTPException(status_code=404, detail=f"Unknown user: {user_id}")


# --- Preview & dispatch ----------------------------------------------------


@router.get("/users/{user_id}/preview", response_model=List[TopJobMatch])
def preview_matches(
    user_id: str,
    top_n: int = Query(DEFAULT_TOP_N, ge=1, le=10),
    include_recent: bool = Query(
        False,
        description="Include jobs already sent in the last 7 days.",
    ),
    db: Session = Depends(get_db),
):
    """Exactly what the next digest would contain — without sending anything.

    The settings tab uses this so a user can sanity-check their matches before
    committing to daily delivery.
    """
    user = settings_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown user: {user_id}")

    exclude = set() if include_recent else recently_notified_job_ids(db, user_id)
    return get_top_matches(
        db,
        user,
        top_n=top_n,
        exclude_job_ids=exclude,
        app_base_url=os.getenv("APP_BASE_URL", ""),
    )


@router.post("/users/{user_id}/send-test")
def send_test_digest(
    user_id: str,
    dry_run: bool = Query(False, description="Render and pick a channel, but do not transmit."),
    db: Session = Depends(get_db),
):
    """Send this user's digest right now, bypassing the once-per-day guard.

    The "Send test" button in the settings tab. `force=True` so a user testing
    their setup is not told "already sent today".
    """
    user = settings_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown user: {user_id}")

    outcome, results = send_digest_for_user(db, user, force=True, dry_run=dry_run)
    return {"outcome": outcome, "results": [r.model_dump() for r in results]}


@router.post("/dispatch", response_model=DispatchSummary)
def trigger_dispatch(
    dry_run: bool = Query(False),
    force: bool = Query(False, description="Ignore the once-per-day guard."),
    respect_send_hour: bool = Query(
        False,
        description="Only send to users whose local send hour is now. The scheduler sets this True; manual runs default False.",
    ),
    db: Session = Depends(get_db),
):
    """Run the whole digest on demand — for the demo, and for debugging.

    NOTE (Omar Zahran): this endpoint is unauthenticated, like every other
    route in this app today. Before anything is deployed publicly it needs to
    be gated — it sends real messages to every user. See docs/notifications.md.
    """
    return run_daily_dispatch(
        db, force=force, dry_run=dry_run, respect_send_hour=respect_send_hour
    )


# --- Diagnostics -----------------------------------------------------------


@router.get("/scheduler", response_model=dict)
def scheduler_status():
    return get_scheduler_status()


@router.get("/providers", response_model=List[ProviderStatus])
def provider_status():
    """Which channels are actually usable right now.

    First thing to check when a digest does not arrive.
    """
    return [
        ProviderStatus(
            channel=provider.channel,
            name=provider.name,
            configured=provider.is_configured(),
        )
        for provider in build_provider_chain()
    ]


@router.get("/logs", response_model=List[NotificationLogOut])
def recent_logs(
    user_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(NotificationLogORM)
    if user_id:
        query = query.filter(NotificationLogORM.user_id == user_id)

    rows = query.order_by(NotificationLogORM.created_at.desc()).limit(limit).all()
    return [
        NotificationLogOut(
            id=row.id,
            user_id=row.user_id,
            channel=row.channel,
            provider=row.provider,
            status=row.status,
            job_ids=row.job_ids or [],
            error_message=row.error_message,
            sent_on_local_date=row.sent_on_local_date,
        )
        for row in rows
    ]
