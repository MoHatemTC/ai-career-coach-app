"""Email delivery over SMTP.

This is the fallback channel named in the brief, and the one most likely to
actually carry the feature on demo day (see the WhatsApp template constraint
in postpeer.py). It is implemented properly — multipart/alternative, STARTTLS,
console mode for local dev — rather than as a placeholder.

Uses the EMAIL_* variables already declared in .env.example, so no new naming
convention is introduced.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import uuid
from email.message import EmailMessage

from backend.features.notifications.providers.base import NotificationProvider
from backend.features.notifications.renderer import (
    render_email_html,
    render_email_subject,
    render_email_text,
)
from backend.features.notifications.schema import DeliveryResult, DigestPayload

logger = logging.getLogger(__name__)


class SmtpEmailProvider(NotificationProvider):
    channel = "email"
    name = "smtp"

    def __init__(self) -> None:
        self.host = os.getenv("EMAIL_HOST", "")
        self.port = int(os.getenv("EMAIL_PORT") or 587)
        self.username = os.getenv("EMAIL_USERNAME", "")
        self.password = os.getenv("EMAIL_PASSWORD", "")
        self.sender = os.getenv("EMAIL_FROM", "") or self.username
        self.use_tls = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
        self.timeout_seconds = int(os.getenv("EMAIL_TIMEOUT_SECONDS", "20"))
        self.app_base_url = os.getenv("APP_BASE_URL", "")

        # With no SMTP host configured, print the digest to stdout instead of
        # failing. Lets the whole pipeline be demoed and tested end-to-end
        # without credentials — and makes it obvious nothing really sent.
        self.console_mode = os.getenv("EMAIL_CONSOLE_FALLBACK", "true").lower() == "true"

    def is_configured(self) -> bool:
        if self.host and self.sender:
            return True
        return self.console_mode

    def _build_message(self, payload: DigestPayload, recipient: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = render_email_subject(payload)
        message["From"] = self.sender or "career-coach@localhost"
        message["To"] = recipient

        # Gives well-behaved clients a native unsubscribe control, and is a
        # meaningful deliverability signal for bulk mail.
        if self.app_base_url:
            message["List-Unsubscribe"] = f"<{self.app_base_url.rstrip('/')}/settings>"

        message.set_content(render_email_text(payload, self.app_base_url))
        message.add_alternative(
            render_email_html(payload, self.app_base_url), subtype="html"
        )
        return message

    def send(self, payload: DigestPayload, recipient: str) -> DeliveryResult:
        if not payload.matches:
            return DeliveryResult.failed(self.channel, self.name, "no matches to send")

        try:
            message = self._build_message(payload, recipient)
        except Exception as exc:
            logger.exception("Failed to render digest for %s", payload.user_id)
            return DeliveryResult.failed(self.channel, self.name, f"render failed: {exc}")

        if not self.host:
            if not self.console_mode:
                return DeliveryResult.failed(
                    self.channel, self.name, "EMAIL_HOST is not configured"
                )
            print("=" * 72)
            print(f"[console-email] would send to {recipient}")
            print(f"[console-email] subject: {message['Subject']}")
            print("-" * 72)
            print(render_email_text(payload, self.app_base_url))
            print("=" * 72)
            return DeliveryResult.ok(
                self.channel, "console", f"console-{uuid.uuid4().hex[:12]}"
            )

        try:
            if self.port == 465:
                smtp_class = smtplib.SMTP_SSL
                context = ssl.create_default_context()
                with smtp_class(
                    self.host, self.port, timeout=self.timeout_seconds, context=context
                ) as server:
                    if self.username:
                        server.login(self.username, self.password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(
                    self.host, self.port, timeout=self.timeout_seconds
                ) as server:
                    if self.use_tls:
                        server.starttls(context=ssl.create_default_context())
                    if self.username:
                        server.login(self.username, self.password)
                    server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("SMTP send failed for %s: %s", payload.user_id, exc)
            return DeliveryResult.failed(self.channel, self.name, f"smtp failed: {exc}")

        # SMTP gives no message id back, so we mint one to correlate logs.
        return DeliveryResult.ok(self.channel, self.name, f"smtp-{uuid.uuid4().hex[:12]}")
