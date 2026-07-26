"""Read/write user contact + notification settings.

Route handlers stay thin per CONTRIBUTING ("Routes should handle HTTP
request/response logic only"); all the merge logic lives here.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.db_models import UserORM
from backend.models.user import (
    NotificationSettings,
    NotificationSettingsUpdate,
    ProfileSnapshot,
    UserCreate,
    UserRead,
)

_SETTINGS_FIELDS = (
    "email",
    "phone",
    "notifications_enabled",
    "notify_via_whatsapp",
    "notify_via_email",
    "min_match_score",
    "send_hour_local",
    "timezone",
)

_PROFILE_FIELDS = (
    "current_title",
    "skills",
    "experience_years",
    "summary",
    "location",
    "preferred_work_type",
    "salary_expectation",
)


def to_user_read(row: UserORM) -> UserRead:
    """Flat ORM row -> nested API shape."""
    return UserRead(
        user_id=row.user_id,
        full_name=row.full_name or "",
        settings=NotificationSettings(
            email=row.email,
            phone=row.phone,
            notifications_enabled=bool(row.notifications_enabled),
            notify_via_whatsapp=bool(row.notify_via_whatsapp),
            notify_via_email=bool(row.notify_via_email),
            min_match_score=row.min_match_score if row.min_match_score is not None else 40.0,
            send_hour_local=row.send_hour_local if row.send_hour_local is not None else 8,
            timezone=row.timezone or "Africa/Cairo",
        ),
        profile=ProfileSnapshot(
            current_title=row.current_title or "",
            skills=row.skills or [],
            experience_years=row.experience_years or 0,
            summary=row.summary or "",
            location=row.location or "",
            preferred_work_type=row.preferred_work_type or "",
            salary_expectation=row.salary_expectation or 0,
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_user(db: Session, user_id: str) -> Optional[UserRead]:
    row = db.query(UserORM).filter(UserORM.user_id == user_id).first()
    return to_user_read(row) if row else None


def list_users(db: Session, only_enabled: bool = False) -> List[UserRead]:
    query = db.query(UserORM)
    if only_enabled:
        query = query.filter(UserORM.notifications_enabled.is_(True))
    return [to_user_read(row) for row in query.all()]


def list_notifiable_users(db: Session) -> List[UserRead]:
    """Users the scheduler should attempt tonight.

    Coarse filter in SQL (notifications_enabled), then the precise
    "is there actually a usable address on an enabled channel" check in
    Python via `UserRead.is_reachable()` — that condition spans four columns
    and is far clearer as code than as a SQL boolean expression.
    """
    return [user for user in list_users(db, only_enabled=True) if user.is_reachable()]


def upsert_user(db: Session, payload: UserCreate) -> UserRead:
    """Create the user, or overwrite the supplied fields if they exist."""
    row = db.query(UserORM).filter(UserORM.user_id == payload.user_id).first()
    if row is None:
        row = UserORM(user_id=payload.user_id)
        db.add(row)

    row.full_name = payload.full_name

    settings_data = payload.settings.model_dump()
    for field in _SETTINGS_FIELDS:
        setattr(row, field, settings_data[field])

    profile_data = payload.profile.model_dump()
    for field in _PROFILE_FIELDS:
        setattr(row, field, profile_data[field])

    db.commit()
    db.refresh(row)
    return to_user_read(row)


def update_settings(
    db: Session, user_id: str, patch: NotificationSettingsUpdate
) -> Optional[UserRead]:
    """Apply a partial settings update. Returns None if the user is unknown.

    `exclude_unset=True` is what makes PATCH semantics correct: a field the
    client never mentioned is left alone, while a field explicitly sent as
    null is cleared.
    """
    row = db.query(UserORM).filter(UserORM.user_id == user_id).first()
    if row is None:
        return None

    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return to_user_read(row)


def update_profile_snapshot(
    db: Session, user_id: str, profile: ProfileSnapshot
) -> Optional[UserRead]:
    """Refresh the matching inputs for a user.

    INTEGRATION POINT (Omar Zahran / CV lane): call this right after
    `/upload` parses a CV, so the nightly digest scores against the newest
    profile instead of whatever was stored at signup.
    """
    row = db.query(UserORM).filter(UserORM.user_id == user_id).first()
    if row is None:
        return None

    profile_data = profile.model_dump()
    for field in _PROFILE_FIELDS:
        setattr(row, field, profile_data[field])

    db.commit()
    db.refresh(row)
    return to_user_read(row)


def delete_user(db: Session, user_id: str) -> bool:
    """Hard-delete a user. Supports the PRD 9 (S) "user control" requirement."""
    row = db.query(UserORM).filter(UserORM.user_id == user_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
