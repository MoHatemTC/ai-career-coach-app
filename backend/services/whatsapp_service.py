import logging

logger = logging.getLogger(__name__)


def send_whatsapp(recipient: str, message: str) -> bool:
    """
    Placeholder WhatsApp sender.

    Replace this implementation later with Twilio,
    Meta Cloud API or whichever provider the team chooses.
    """

    try:
        logger.info(
            "WhatsApp notification queued for %s\n%s",
            recipient,
            message,
        )

        return True

    except Exception:
        logger.exception("Failed to send WhatsApp message.")
        return False