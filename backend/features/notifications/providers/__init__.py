"""Provider registry.

Providers are constructed per run rather than at import time so that a change
to `.env` takes effect on the next dispatch without restarting the API.
"""

from __future__ import annotations

from typing import List

from backend.features.notifications.providers.base import NotificationProvider
from backend.features.notifications.providers.email_smtp import SmtpEmailProvider
from backend.features.notifications.providers.postpeer import PostpeerWhatsAppProvider

__all__ = [
    "NotificationProvider",
    "PostpeerWhatsAppProvider",
    "SmtpEmailProvider",
    "build_provider_chain",
]


def build_provider_chain() -> List[NotificationProvider]:
    """Providers in fallback order: WhatsApp first, then email.

    Order encodes the brief: "WhatsApp through Postpeer as the primary
    channel. Fall back to email if WhatsApp integration is not feasible."
    The dispatcher walks this list and stops at the first success, so an
    unconfigured or failing Postpeer degrades to email automatically instead
    of dropping the digest.
    """
    return [PostpeerWhatsAppProvider(), SmtpEmailProvider()]
