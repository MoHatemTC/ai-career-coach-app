# backend/services/email_service.py
import os
import logging

logger = logging.getLogger(__name__)

class EmailSenderStub:
    def __init__(self):
        # قراءة الإعدادات من الـ Environment Variables (تسهيلاً للتاسك)
        self.email_enabled = os.getenv("EMAIL_ENABLED", "True").lower() == "true"
        self.sender_address = os.getenv("SENDER_EMAIL", "no-reply@automationsystem.com")
        logger.info(f"[EmailStub] Initialized. Enabled: {self.email_enabled}, Sender: {self.sender_address}")

    def send_email(self, recipient_email: str, subject: str, body: str) -> bool:
        if not self.email_enabled:
            logger.info(f"[EmailStub] Email simulation is disabled for: {recipient_email}")
            return False
        
        logger.info("=" * 60)
        logger.info(f"[EmailStub] >>> SIMULATING EMAIL SENT <<<")
        logger.info(f"From: {self.sender_address}")
        logger.info(f"To: {recipient_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body: {body}")
        logger.info("=" * 60)
        return True