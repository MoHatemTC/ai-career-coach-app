"""Notification settings routes — where a user's email/phone are stored.

Thin HTTP layer only. Settings are persisted to the `notification_settings`
SQLite table (not an in-memory dict) so they survive a backend restart, and so
the notifications lane can read them independently via
`GET /notifications/settings/{user_id}` without going through this UI.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.models.db_models import NotificationSettings
from backend.services.database import get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# Single-user demo: the UI has no auth yet, so everything is stored under one
# id. Kept as an explicit parameter throughout so multi-user is a UI change,
# not a schema change.
DEFAULT_USER_ID = "default"


class NotificationSettingsIn(BaseModel):
    user_id: str = DEFAULT_USER_ID
    email: Optional[str] = None
    phone: Optional[str] = None


class NotificationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: Optional[str]
    phone: Optional[str]


@router.post("/settings", response_model=NotificationSettingsOut)
def save_settings(
    payload: NotificationSettingsIn, db: Session = Depends(get_db)
) -> NotificationSettings:
    """Create or update a user's notification settings (upsert by user_id)."""
    row = db.get(NotificationSettings, payload.user_id)
    if row is None:
        row = NotificationSettings(user_id=payload.user_id)
        db.add(row)
    row.email = payload.email
    row.phone = payload.phone
    db.commit()
    db.refresh(row)
    return row


@router.get("/settings/{user_id}", response_model=NotificationSettingsOut)
def get_settings(
    user_id: str, db: Session = Depends(get_db)
) -> NotificationSettings:
    """Read a user's settings. Used by the UI to prefill, and by the
    notifications lane to find out where to send things."""
    row = db.get(NotificationSettings, user_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No notification settings for user {user_id!r}."
        )
    return row
