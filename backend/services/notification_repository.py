from sqlalchemy.orm import Session

from backend.models.db_models import NotificationSettingsORM
from backend.models.profile import Profile


def get_notification_settings(
    db: Session,
    profile_id: int,
):
    """
    Retrieve notification settings for a user.
    """
    return (
        db.query(NotificationSettingsORM)
        .filter(NotificationSettingsORM.profile_id == profile_id)
        .first()
    )


def get_profile(
    db: Session,
    profile_id: int,
):
    """
    Retrieve the user's profile.
    """
    return (
        db.query(Profile)
        .filter(Profile.id == profile_id)
        .first()
    )


def notifications_enabled(
    settings: NotificationSettingsORM,
) -> bool:
    """
    Check whether notifications are enabled.
    """
    if settings is None:
        return False

    return settings.enabled


def should_notify(
    match_score: float,
    threshold: float,
) -> bool:
    """
    Check whether the match score passes the user's threshold.
    """
    return match_score >= threshold


def get_notification_channel(
    settings: NotificationSettingsORM,
) -> str:
    """
    Return the configured notification channel.
    """
    return settings.channel


def get_notification_time(
    settings: NotificationSettingsORM,
) -> str:
    """
    Return the configured notification time.
    """
    return settings.notification_time