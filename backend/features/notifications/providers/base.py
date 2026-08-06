"""Provider interface for digest delivery.

Follows the same shape as `BaseJobIngestionClient` in
`backend/services/ingestion.py` — one abstract base, one concrete class per
external service — so the pattern is already familiar in this codebase.

Why an interface at all, when the PRD names one vendor? Because the brief
itself says to fall back to email "if WhatsApp integration is not feasible".
That fallback is only cheap if both channels sit behind the same call
signature. It also keeps the Postpeer specifics quarantined in one file until
its API is confirmed.
"""

from __future__ import annotations

import abc

from backend.features.notifications.schema import DeliveryResult, DigestPayload


class NotificationProvider(abc.ABC):
    """Sends one rendered digest to one recipient over one channel."""

    #: "whatsapp" | "email" — recorded on NotificationLogORM.channel
    channel: str = ""

    #: Short stable id for logs, e.g. "postpeer", "smtp".
    name: str = ""

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """True when every credential this provider needs is present.

        Checked *before* a send so a misconfigured provider degrades to the
        fallback channel instead of raising per-user at send time.
        """

    @abc.abstractmethod
    def send(self, payload: DigestPayload, recipient: str) -> DeliveryResult:
        """Deliver the digest.

        Implementations must not raise for expected failures (network error,
        provider 4xx/5xx, malformed recipient) — return
        `DeliveryResult.failed(...)` instead. A raise here would abort the
        nightly run for every remaining user.
        """
