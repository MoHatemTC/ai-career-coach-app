"""Reads `notification_settings` rows into something the dispatcher can send to.

There is deliberately no second user table here. Contract 6 (see
`backend/routes/notifications.py` and `docs/notification-parameters.md`) already
owns contact details, and the frontend already writes them; a parallel store
would give the app two answers to "what is this user's email".

What this module adds is the translation from *stored preferences* to *sending
decisions*:

    notification_channels  -> which providers may be tried
    relevance_threshold    -> a 0-100 floor on match_score
    frequency              -> how far apart two digests may be
    profile_snapshot       -> the matching input, since a 9am cron job has no
                              browser session to read a profile out of

Route handlers stay thin per CONTRIBUTING; the merge logic lives here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.models.db_models import NotificationSettings

logger = logging.getLogger(__name__)

# Mirrors the defaults applied on write in backend/routes/notifications.py, so
# a row saved before these columns existed behaves like a freshly-saved one
# rather than like a user who chose 00:00 UTC.
DEFAULT_SEND_HOUR_LOCAL = 8
DEFAULT_TIMEZONE = "Africa/Cairo"
DEFAULT_RELEVANCE_THRESHOLD = 0.75
DEFAULT_FREQUENCY = "daily"

# How many days apart two digests may be, per stored frequency value.
FREQUENCY_INTERVAL_DAYS = {"daily": 1, "weekly": 7}

# E.164: leading "+", country code, at most 15 digits in total.
_E164_MAX_DIGITS = 15
_E164_MIN_DIGITS = 8


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Normalize a phone number to E.164 (`+201234567890`), or None.

    WhatsApp providers reject anything that is not E.164, and on some plans
    they reject it *silently* — the send is accepted and the message never
    arrives. Normalizing here means "+20 (10) 1234-5678" and "0020101234567"
    both reach the provider in the one form it accepts.

    Returns None rather than raising for an unusable value: the settings form
    accepts free text by contract, and a malformed number should cost that user
    their WhatsApp channel, not abort the run.
    """
    if raw is None:
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    digits = "".join(char for char in stripped if char.isdigit())
    if stripped.startswith("00"):
        digits = digits[2:]

    if not (_E164_MIN_DIGITS <= len(digits) <= _E164_MAX_DIGITS):
        logger.warning(
            "Phone %r is not usable as E.164 (%s digits); WhatsApp disabled for it",
            stripped,
            len(digits),
        )
        return None

    return f"+{digits}"


def resolve_timezone(name: Optional[str]) -> ZoneInfo:
    """Load an IANA zone, falling back to the default and then to UTC.

    Never raises. A bad timezone string is a settings-form problem; letting it
    become an exception on a background thread turns it into a silent outage
    for every user after this one in the loop.
    """
    for candidate in (name, DEFAULT_TIMEZONE):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("Unusable timezone %r; falling back", candidate)
    return ZoneInfo("UTC")


@dataclass
class DigestRecipient:
    """One user, resolved down to everything a send needs and nothing else."""

    user_id: str
    full_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    channels: List[str] = field(default_factory=list)
    frequency: str = DEFAULT_FREQUENCY
    #: 0-100 floor on match_score, scaled from the stored 0-1 threshold.
    min_match_score: float = DEFAULT_RELEVANCE_THRESHOLD * 100
    send_hour_local: int = DEFAULT_SEND_HOUR_LOCAL
    timezone: str = DEFAULT_TIMEZONE
    profile: Dict[str, Any] = field(default_factory=dict)

    def wants(self, channel: str) -> bool:
        return channel in self.channels

    def address_for(self, channel: str) -> Optional[str]:
        """The address to use for this channel, or None if it is unusable."""
        if not self.wants(channel):
            return None
        if channel == "whatsapp":
            return self.phone
        if channel == "email":
            return self.email
        return None

    def is_reachable(self) -> bool:
        """True if at least one selected channel has a usable address."""
        return any(self.address_for(channel) for channel in self.channels)

    def interval_days(self) -> int:
        return FREQUENCY_INTERVAL_DAYS.get(
            (self.frequency or DEFAULT_FREQUENCY).lower(), 1
        )

    def zone(self) -> ZoneInfo:
        return resolve_timezone(self.timezone)


def _decode_json(raw: Optional[str], fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Ignoring malformed JSON in notification_settings: %.80r", raw)
        return fallback


def to_recipient(row: NotificationSettings) -> DigestRecipient:
    """Flat ORM row -> the sending view of that user."""
    channels = _decode_json(row.notification_channels, [])
    if not isinstance(channels, list):
        channels = []

    profile = _decode_json(row.profile_snapshot, {})
    if not isinstance(profile, dict):
        profile = {}

    threshold = (
        row.relevance_threshold
        if row.relevance_threshold is not None
        else DEFAULT_RELEVANCE_THRESHOLD
    )

    return DigestRecipient(
        user_id=row.user_id,
        full_name=row.full_name or "",
        email=(row.email or "").strip() or None,
        # Normalized on read rather than on write: the settings contract
        # accepts free-text phone numbers and breaking that would break the
        # form the frontend already ships.
        phone=normalize_phone(row.phone),
        channels=[str(channel).lower() for channel in channels],
        frequency=row.frequency or DEFAULT_FREQUENCY,
        # Stored 0-1 (Contract 6), compared against a 0-100 match score.
        min_match_score=float(threshold) * 100.0,
        send_hour_local=(
            row.send_hour_local
            if row.send_hour_local is not None
            else DEFAULT_SEND_HOUR_LOCAL
        ),
        timezone=row.timezone or DEFAULT_TIMEZONE,
        profile=profile,
    )


def get_recipient(db: Session, user_id: str) -> Optional[DigestRecipient]:
    row = db.get(NotificationSettings, user_id)
    return to_recipient(row) if row is not None else None


def list_recipients(db: Session, reachable_only: bool = True) -> List[DigestRecipient]:
    """Everyone the dispatcher could send to.

    The "is there actually a usable address on a selected channel" test spans
    four columns and a JSON blob, so it is done in Python rather than as a SQL
    predicate — at single-user demo scale the difference is not measurable, and
    the condition is far clearer as code.
    """
    recipients = [to_recipient(row) for row in db.query(NotificationSettings).all()]
    if not reachable_only:
        return recipients
    return [recipient for recipient in recipients if recipient.is_reachable()]


def save_profile_snapshot(
    db: Session, user_id: str, profile: Dict[str, Any]
) -> Optional[DigestRecipient]:
    """Store the matching inputs the scheduler will score against.

    Called from `PUT /notifications/settings/{user_id}/profile`, which the
    frontend hits after a CV is parsed. Without this the digest can only run
    for users who happen to have a browser tab open, which is the opposite of
    what an unprompted daily notification is for.
    """
    row = db.get(NotificationSettings, user_id)
    if row is None:
        return None

    row.profile_snapshot = json.dumps(profile)
    # The digest greets the user by name, and the CV is the only place the app
    # learns one. Taken opportunistically rather than as a separate field.
    name = profile.get("name") or profile.get("full_name")
    if name and not row.full_name:
        row.full_name = str(name)

    db.commit()
    db.refresh(row)
    return to_recipient(row)
