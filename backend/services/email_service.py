import logging
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")


def send_email(
    recipient: str,
    subject: str,
    body: str,
) -> bool:
    """
    Send an email notification.

    Returns:
        True if the email was sent successfully.
        False otherwise.
    """
    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = EMAIL_FROM
        message["To"] = recipient
        message.set_content(body)

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(message)

        logger.info("Email sent successfully to %s", recipient)
        return True

    except Exception:
        logger.exception("Failed to send email to %s", recipient)
        return False