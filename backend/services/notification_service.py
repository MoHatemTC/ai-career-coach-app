import logging
from typing import List

from sqlalchemy.orm import Session

from backend.models.profile import Profile
from backend.models.db_models import NotificationSettingsORM
from backend.services.email_service import send_email
from backend.services.whatsapp_service import send_whatsapp
from backend.services.notification_repository import (
    get_notification_settings,
    get_profile,
    notifications_enabled,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Coordinates notification delivery.
    """

    def notify_user(
        self,
        db: Session,
        profile_id: int,
        ranked_jobs: List[dict],
    ) -> bool:

        settings = get_notification_settings(db, profile_id)

        if settings is None:
            logger.warning(
                "No notification settings found for profile %s",
                profile_id,
            )
            return False

        if not notifications_enabled(settings):
            logger.info(
                "Notifications disabled for profile %s",
                profile_id,
            )
            return False

        profile = get_profile(db, profile_id)

        if profile is None:
            logger.warning(
                "Profile %s not found",
                profile_id,
            )
            return False

        threshold = settings.relevance_threshold

        jobs = [
            job
            for job in ranked_jobs
            if job["match_score"] >= threshold
        ]

        if not jobs:
            logger.info(
                "No jobs exceeded threshold for profile %s",
                profile_id,
            )
            return False

        subject = f"{len(jobs)} New Job Matches"

        body = self._build_message(profile.name, jobs)

        try:

            if settings.channel.lower() == "email":

                return send_email(
                    recipient=profile.email,
                    subject=subject,
                    body=body,
                )

            elif settings.channel.lower() == "whatsapp":

                return send_whatsapp(
                    recipient=profile.phone,
                    message=body,
                )

            logger.warning(
                "Unknown notification channel %s",
                settings.channel,
            )

            return False

        except Exception:

            logger.exception(
                "Notification delivery failed."
            )

            return False

    @staticmethod
    def notify_all_users(self, db: Session):
        """
        Entry point used by the scheduler.

        TODO:
            Retrieve all users with notifications enabled.
            Retrieve ranked jobs for each user.
            Call notify_user().
        """

        logger.info("Starting notification workflow.")

        try:
            logger.info(
                "Waiting for matching integration."
            )

            # Future implementation:
            #
            # settings = db.query(NotificationSettingsORM)\
            #     .filter(NotificationSettingsORM.enabled == True)\
            #     .all()
            #
            # for setting in settings:
            #
            #     ranked_jobs = matching_service.rank_jobs(...)
            #
            #     self.notify_user(
            #         db=db,
            #         profile_id=setting.profile_id,
            #         ranked_jobs=ranked_jobs,
            #     )

        except Exception:
            logger.exception(
                "Notification workflow failed."
            )

    @staticmethod
    def _build_message(
        name: str,
        jobs: List[dict],
    ) -> str:

        lines = [
            f"Hello {name},",
            "",
            f"We found {len(jobs)} new job matches for you.",
            "",
        ]

        for job in jobs:
            lines.append(
                f"• {job['title']} - {job['company']} ({job['match_score']:.1f}%)"
            )

        lines.extend(
            [
                "",
                "Open AI Career Coach to view full details.",
            ]
        )

        return "\n".join(lines)