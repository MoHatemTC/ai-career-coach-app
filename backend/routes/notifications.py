"""Notification settings routes — the store the notifications lane reads.

Thin HTTP layer only. Settings are persisted to the `notification_settings`
SQLite table (not an in-memory dict) so they survive a backend restart, and so
the notifications lane can read them independently via
`GET /notifications/settings/{user_id}` without going through this UI.

THE CONTRACT (Contract 6 in the pipeline plan: settings tab -> notifications)
----------------------------------------------------------------------------
`GET` returns, and `POST` accepts:

    {
      "user_id": "default",
      "contact": { "email": "...", "phone_whatsapp": "+20..." },
      "notification_channels": ["email", "whatsapp"],
      "frequency": "daily",
      "relevance_threshold": 0.75
    }

`contact` is nested because that is the agreed shape; the table stores the
fields flat, since that is what SQLite can index. The nesting is applied here,
at the boundary.

The flat `{"email": ..., "phone": ...}` form is still accepted on POST, because
that is what the Streamlit settings form sends and there is no reason to break
it. Nested wins if both are given.

Note on channels: the plan lists `email` and `whatsapp`, while PRD 7.8
specifies email only for v1. Both are storable; which are actually honoured is
the sender's decision, not this endpoint's.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models.db_models import NotificationSettings
from backend.services.database import get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# Single-user demo: the UI has no auth yet, so everything is stored under one
# id. Kept as an explicit parameter throughout so multi-user is a UI change,
# not a schema change.
DEFAULT_USER_ID = "default"

# Defaults match the plan's example, so a freshly-saved row is already a valid
# Contract 6 payload rather than a half-populated one.
DEFAULT_CHANNELS = ["email"]
DEFAULT_FREQUENCY = "daily"
DEFAULT_RELEVANCE_THRESHOLD = 0.75


class Contact(BaseModel):
    email: Optional[str] = None
    phone_whatsapp: Optional[str] = None


class NotificationSettingsIn(BaseModel):
    user_id: str = DEFAULT_USER_ID
    contact: Optional[Contact] = None
    notification_channels: Optional[List[str]] = None
    frequency: Optional[str] = None
    relevance_threshold: Optional[float] = None

    # Legacy flat fields, still sent by the Streamlit settings form.
    email: Optional[str] = None
    phone: Optional[str] = None

    def resolved_email(self) -> Optional[str]:
        if self.contact is not None and self.contact.email is not None:
            return self.contact.email
        return self.email

    def resolved_phone(self) -> Optional[str]:
        if self.contact is not None and self.contact.phone_whatsapp is not None:
            return self.contact.phone_whatsapp
        return self.phone


class NotificationSettingsOut(BaseModel):
    user_id: str
    contact: Contact
    notification_channels: List[str] = Field(default_factory=list)
    frequency: Optional[str] = None
    relevance_threshold: Optional[float] = None


def _to_contract(row: NotificationSettings) -> NotificationSettingsOut:
    """Render a flat row as the nested Contract 6 payload."""
    try:
        channels = json.loads(row.notification_channels or "[]")
    except json.JSONDecodeError:
        channels = []
    return NotificationSettingsOut(
        user_id=row.user_id,
        contact=Contact(email=row.email, phone_whatsapp=row.phone),
        notification_channels=channels,
        frequency=row.frequency,
        relevance_threshold=row.relevance_threshold,
    )


@router.post("/settings", response_model=NotificationSettingsOut)
def save_settings(
    payload: NotificationSettingsIn, db: Session = Depends(get_db)
) -> NotificationSettingsOut:
    """Create or update a user's notification settings (upsert by user_id)."""
    row = db.get(NotificationSettings, payload.user_id)
    if row is None:
        row = NotificationSettings(user_id=payload.user_id)
        db.add(row)

    row.email = payload.resolved_email()
    row.phone = payload.resolved_phone()
    # An omitted preference keeps whatever is stored rather than being blanked,
    # so the UI's contact-only form cannot silently reset the others.
    if payload.notification_channels is not None:
        row.notification_channels = json.dumps(payload.notification_channels)
    elif row.notification_channels is None:
        row.notification_channels = json.dumps(DEFAULT_CHANNELS)
    if payload.frequency is not None:
        row.frequency = payload.frequency
    elif row.frequency is None:
        row.frequency = DEFAULT_FREQUENCY
    if payload.relevance_threshold is not None:
        row.relevance_threshold = payload.relevance_threshold
    elif row.relevance_threshold is None:
        row.relevance_threshold = DEFAULT_RELEVANCE_THRESHOLD

    db.commit()
    db.refresh(row)
    return _to_contract(row)


@router.get("/settings/{user_id}", response_model=NotificationSettingsOut)
def get_settings(
    user_id: str, db: Session = Depends(get_db)
) -> NotificationSettingsOut:
    """Read a user's settings. Used by the UI to prefill, and by the
    notifications lane to find out where and how to send."""
    row = db.get(NotificationSettings, user_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No notification settings for user {user_id!r}."
        )
    return _to_contract(row)
