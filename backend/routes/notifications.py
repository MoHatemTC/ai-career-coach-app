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

Since delivery landed, the payload also carries three optional scheduling
fields — `full_name`, `send_hour_local`, `timezone`. They are additive: a
client that omits them keeps whatever is stored, and a client that ignores them
on read is unaffected. They exist because a scheduled digest has no browser
session to ask "who is this and when is their morning?".

Note on channels: `email` and `whatsapp` are both storable and, since the
notifications feature landed, both are honoured — see
`backend/features/notifications/providers/`. Which one a given user actually
receives on depends on which are selected here and which are configured in the
environment; the chain tries WhatsApp first and falls back to email.
"""

import json
from typing import List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
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
# Kept in step with backend/features/notifications/settings_service.py, which
# applies the same values when reading a row saved before these columns
# existed.
DEFAULT_SEND_HOUR_LOCAL = 8
DEFAULT_TIMEZONE = "Africa/Cairo"


class _Unset:
    """Sentinel for "the client did not mention this field".

    `None` cannot carry that meaning here, because `None` is also the way a
    client clears a stored address.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNSET"


UNSET = _Unset()


class Contact(BaseModel):
    email: Optional[str] = None
    phone_whatsapp: Optional[str] = None


class NotificationSettingsIn(BaseModel):
    user_id: str = DEFAULT_USER_ID
    contact: Optional[Contact] = None
    notification_channels: Optional[List[str]] = None
    frequency: Optional[str] = None
    relevance_threshold: Optional[float] = None

    # Scheduling. Optional like every other preference: omitted means "leave
    # what is stored", not "reset to default".
    full_name: Optional[str] = None
    send_hour_local: Optional[int] = Field(default=None, ge=0, le=23)
    timezone: Optional[str] = None

    # Legacy flat fields, still sent by the Streamlit settings form.
    email: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: Optional[str]) -> Optional[str]:
        """Reject a zone `ZoneInfo` cannot load.

        Validated on write because an unknown zone that reaches the database
        turns one bad form value into a permanent problem: every later read of
        that user has to guess, and the digest silently goes out at the wrong
        local hour rather than failing anywhere visible.
        """
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value

    def _resolve(self, nested_field: str, flat_field: str):
        """Return the supplied contact value, or `UNSET` if it was omitted.

        Distinguishing "omitted" from "sent as null" is the whole point. These
        two used to return `None` for both, and the caller assigned that None
        straight onto the row — so any POST that did not happen to carry
        contact details silently erased the stored email and phone. The React
        form always sends them, which is why it never showed up there; a
        `{"relevance_threshold": 0.3}` write from anywhere else destroyed the
        only copy of the user's address.

        `model_fields_set` is what makes the distinction: a field the client
        never mentioned is absent from it, while an explicit `null` is present
        and still means "clear this".
        """
        if self.contact is not None and nested_field in self.contact.model_fields_set:
            return getattr(self.contact, nested_field)
        if flat_field in self.model_fields_set:
            return getattr(self, flat_field)
        return UNSET

    def resolved_email(self):
        return self._resolve("email", "email")

    def resolved_phone(self):
        return self._resolve("phone_whatsapp", "phone")


class NotificationSettingsOut(BaseModel):
    user_id: str
    contact: Contact
    notification_channels: List[str] = Field(default_factory=list)
    frequency: Optional[str] = None
    relevance_threshold: Optional[float] = None
    full_name: Optional[str] = None
    send_hour_local: Optional[int] = None
    timezone: Optional[str] = None


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
        full_name=row.full_name,
        send_hour_local=row.send_hour_local,
        timezone=row.timezone,
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

    # Contact follows the same omitted-means-keep rule as the preferences
    # below. An explicit null still clears.
    email = payload.resolved_email()
    if email is not UNSET:
        row.email = email
    phone = payload.resolved_phone()
    if phone is not UNSET:
        row.phone = phone
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
    if payload.full_name is not None:
        row.full_name = payload.full_name
    if payload.send_hour_local is not None:
        row.send_hour_local = payload.send_hour_local
    elif row.send_hour_local is None:
        row.send_hour_local = DEFAULT_SEND_HOUR_LOCAL
    if payload.timezone is not None:
        row.timezone = payload.timezone
    elif row.timezone is None:
        row.timezone = DEFAULT_TIMEZONE

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
