"""User + notification-settings schemas.

Why this module exists
----------------------
Before this lane, `Profile` (backend/models/profile.py) was only ever a
request body — it was never stored. That works for on-demand matching
("here is my profile, rank these jobs") but the daily-digest feature has
no caller to supply a profile: the scheduler has to iterate over users on
its own. So we need a persisted user record that carries both:

1. the *contact channels* (email / phone) the digest is delivered to, and
2. a *profile snapshot* the matching pipeline can score against offline.

The profile fields below map 1:1 onto the existing `Profile` model, so the
matching pipeline keeps taking exactly the type it already takes — see
`UserRead.to_profile()`. Nothing in the matching lane had to change shape.

NOTE FOR THE PROFILE LANE (Omar Zahran): if a dedicated `profiles` table
lands later, the intended migration is to drop the profile block here and
have `to_profile()` read from that table instead. The notification code
only ever touches `to_profile()`, so it is the single seam to update.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.models.profile import Profile

# E.164: leading "+", country code, up to 15 digits total.
_E164_MAX_DIGITS = 15


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Normalize a phone number to E.164 (`+201234567890`).

    WhatsApp providers reject anything that is not E.164, and they reject it
    *silently* on some plans (the send is accepted, the message never
    arrives). Normalizing at the edge means a bad number surfaces as a 422 on
    the settings form instead of as a digest that quietly never sends.
    """
    if raw is None:
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    # Users paste numbers as "+20 (10) 1234-5678" or "0020101...".
    digits = "".join(char for char in stripped if char.isdigit())
    if stripped.startswith("00"):
        digits = digits[2:]

    if not digits:
        raise ValueError("phone must contain at least one digit")
    if len(digits) > _E164_MAX_DIGITS:
        raise ValueError(
            f"phone has {len(digits)} digits; E.164 allows at most {_E164_MAX_DIGITS}"
        )
    if len(digits) < 8:
        raise ValueError("phone is too short to be a valid international number")

    return f"+{digits}"


def validate_timezone(value: Optional[str]) -> Optional[str]:
    """Reject anything ZoneInfo cannot load.

    Validated eagerly on write, and on *both* the full and partial models —
    an unknown tz that slips through a PATCH is written to the database and
    then raises on every subsequent read of that user, turning a bad form
    value into a permanent 500.
    """
    if value is None:
        return None

    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA timezone: {value!r}") from exc
    return value


class NotificationSettings(BaseModel):
    """The part of a user record the settings tab writes to."""

    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(
        default=None,
        description="International format. Stored normalized to E.164.",
    )

    notifications_enabled: bool = True
    notify_via_whatsapp: bool = True
    notify_via_email: bool = True

    min_match_score: float = Field(
        default=40.0,
        ge=0.0,
        le=100.0,
        description="Jobs scoring below this are not worth a notification. PRD 7.4 (S).",
    )
    send_hour_local: int = Field(
        default=8,
        ge=0,
        le=23,
        description="Local hour of day to deliver the digest.",
    )
    timezone: str = Field(
        default="Africa/Cairo",
        description="IANA timezone name used to interpret send_hour_local.",
    )

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return normalize_phone(value)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        return validate_timezone(value)


class NotificationSettingsUpdate(BaseModel):
    """PATCH body — every field optional so the form can send partial edits.

    Kept separate from `NotificationSettings` because `None` is ambiguous on a
    partial update: on the full model it means "clear this value", here it
    means "leave this value alone". Merging is done in `settings_service`.
    """

    model_config = ConfigDict(extra="forbid")

    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    notify_via_whatsapp: Optional[bool] = None
    notify_via_email: Optional[bool] = None
    min_match_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    send_hour_local: Optional[int] = Field(default=None, ge=0, le=23)
    timezone: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return normalize_phone(value)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: Optional[str]) -> Optional[str]:
        return validate_timezone(value)


class ProfileSnapshot(BaseModel):
    """Matching inputs stored on the user so the scheduler can score offline."""

    current_title: str = ""
    skills: List[str] = Field(default_factory=list)
    experience_years: int = 0
    summary: str = ""
    location: str = ""
    preferred_work_type: str = ""
    salary_expectation: int = 0


class UserCreate(BaseModel):
    user_id: str
    full_name: str = ""
    settings: NotificationSettings = Field(default_factory=NotificationSettings)
    profile: ProfileSnapshot = Field(default_factory=ProfileSnapshot)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    full_name: str
    settings: NotificationSettings
    profile: ProfileSnapshot
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_profile(self) -> Profile:
        """Adapt the stored snapshot to the `Profile` the matching lane expects.

        This is the *only* coupling between notifications and the profile
        storage shape. Keep it that way.
        """
        return Profile(
            user_id=self.user_id,
            current_title=self.profile.current_title,
            skills=self.profile.skills,
            experience_years=self.profile.experience_years,
            summary=self.profile.summary,
            location=self.profile.location,
            preferred_work_type=self.profile.preferred_work_type,
            salary_expectation=self.profile.salary_expectation,
        )

    def is_reachable(self) -> bool:
        """True if at least one enabled channel has a usable address."""
        if not self.settings.notifications_enabled:
            return False
        if self.settings.notify_via_whatsapp and self.settings.phone:
            return True
        if self.settings.notify_via_email and self.settings.email:
            return True
        return False
