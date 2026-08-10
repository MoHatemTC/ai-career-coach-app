"""Email delivery over SMTP.

This is the fallback channel named in the brief, and the one most likely to
actually carry the feature (see the WhatsApp template constraint in
postpeer.py). It is implemented properly — multipart/alternative, STARTTLS,
console mode for local dev — rather than as a placeholder.

Uses the EMAIL_* variables already declared in .env.example, so no new naming
convention is introduced.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import sys
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


def _print_safely(text: str) -> None:
    """Print text that may contain characters the console cannot encode.

    The digest body carries em-dashes and (on the WhatsApp template) emoji. A
    Windows console still defaults to cp1252, where `print()` of either raises
    UnicodeEncodeError — which the dispatcher would catch and record as a
    delivery *failure*, making console mode look broken on the machines this
    team actually develops on. Degrading unprintable characters to "?" is the
    right trade for a debug channel.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


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
        # failing. Lets the whole pipeline be demoed and tested end to end
        # without credentials — and the banner makes it obvious that nothing
        # really sent, which a silent success would not.
        self.console_mode = (
            os.getenv("EMAIL_CONSOLE_FALLBACK", "true").lower() == "true"
        )

    @property
    def is_console(self) -> bool:
        """True when this will print the digest instead of transmitting it."""
        return not self.host and self.console_mode

    def is_configured(self) -> bool:
        """Whether the dispatcher should try this provider at all.

        Console mode counts, because the point of it is that the whole pipeline
        runs end to end without credentials. It is NOT the same question as
        "will a message actually leave the machine" — see `is_console`, which is
        what any status display must show. Reporting console mode as a
        configured email channel tells someone their delivery is working when
        nothing has been sent, which is the worst thing a diagnostic can do.
        """
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
            base = self.app_base_url.rstrip("/")
            message["List-Unsubscribe"] = f"<{base}/app/settings>"

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
            return DeliveryResult.failed(
                self.channel, self.name, f"render failed: {exc}"
            )

        if not self.host:
            if not self.console_mode:
                return DeliveryResult.failed(
                    self.channel, self.name, "EMAIL_HOST is not configured"
                )
            _print_safely("=" * 72)
            _print_safely(f"[console-email] would send to {recipient}")
            _print_safely(f"[console-email] subject: {message['Subject']}")
            _print_safely("-" * 72)
            _print_safely(render_email_text(payload, self.app_base_url))
            _print_safely("=" * 72)
            return DeliveryResult.ok(
                self.channel, "console", f"console-{uuid.uuid4().hex[:12]}"
            )

        try:
            if self.port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
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

        # SMTP returns no message id, so we mint one to correlate logs.
        return DeliveryResult.ok(
            self.channel, self.name, f"smtp-{uuid.uuid4().hex[:12]}"
        )
