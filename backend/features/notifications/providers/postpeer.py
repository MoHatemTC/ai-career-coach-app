"""WhatsApp delivery via Postpeer.

=============================================================================
 VERIFY THE POSTPEER CONTRACT BEFORE ENABLING IN PROD
=============================================================================
Postpeer's API contract is not in this repository or its history. Rather than
invent an endpoint shape and have it silently 404, every vendor-specific detail
below is driven by an environment variable with a conservative default.

Get these four answers from the Postpeer dashboard, set the vars in `.env`, and
this provider works without a code change:

  1. Base URL and send path        -> POSTPEER_BASE_URL, POSTPEER_SEND_PATH
  2. Auth scheme                   -> POSTPEER_AUTH_STYLE
                                      ("bearer" | "header" | "query")
  3. JSON field names for
     recipient / body / sender     -> POSTPEER_FIELD_TO, POSTPEER_FIELD_BODY,
                                      POSTPEER_FIELD_FROM
  4. Where the provider message id
     appears in the response       -> POSTPEER_RESPONSE_ID_PATH (dotted path)

If the real contract turns out not to fit this shape, `_build_request()` is the
only method to rewrite.

-----------------------------------------------------------------------------
 A CONSTRAINT WORTH RAISING EARLY
-----------------------------------------------------------------------------
On the official WhatsApp Business Platform, a business-initiated message sent
outside the 24-hour customer-service window must use a **pre-approved message
template**; free-form text is rejected. A daily unprompted job digest is
business-initiated by definition, so unless Postpeer resells a number under its
own approved template, this channel needs a template submitted and approved
before it can deliver anything.

That approval is a lead time we do not control, and it is the most likely
reason WhatsApp turns out "not feasible" — which is exactly the case the brief
tells us to fall back to email for. The SMTP provider is therefore implemented
as a first-class channel, not a stub.

Set POSTPEER_TEMPLATE_NAME to send in template mode once approved; leave it
empty for free-form (works in sandbox / inside the 24h window).
=============================================================================
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

from backend.features.notifications.providers.base import NotificationProvider
from backend.features.notifications.renderer import render_whatsapp_text
from backend.features.notifications.schema import DeliveryResult, DigestPayload

logger = logging.getLogger(__name__)


def _dig(data: Any, dotted_path: str) -> Optional[str]:
    """Pull a nested value out of a response body by dotted path.

    Tolerates lists via numeric segments, e.g. "messages.0.id".
    """
    current = data
    for segment in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return str(current)


class PostpeerWhatsAppProvider(NotificationProvider):
    channel = "whatsapp"
    name = "postpeer"

    def __init__(self) -> None:
        self.base_url = os.getenv("POSTPEER_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("POSTPEER_API_KEY", "")
        self.send_path = os.getenv("POSTPEER_SEND_PATH", "/v1/messages")
        self.sender_id = os.getenv("POSTPEER_SENDER_ID", "")

        self.auth_style = os.getenv("POSTPEER_AUTH_STYLE", "bearer").lower()
        self.api_key_header = os.getenv("POSTPEER_API_KEY_HEADER", "Authorization")

        self.field_to = os.getenv("POSTPEER_FIELD_TO", "to")
        self.field_body = os.getenv("POSTPEER_FIELD_BODY", "text")
        self.field_from = os.getenv("POSTPEER_FIELD_FROM", "from")

        self.template_name = os.getenv("POSTPEER_TEMPLATE_NAME", "")
        self.template_language = os.getenv("POSTPEER_TEMPLATE_LANGUAGE", "en")

        self.response_id_path = os.getenv("POSTPEER_RESPONSE_ID_PATH", "id")
        self.timeout_seconds = int(os.getenv("POSTPEER_TIMEOUT_SECONDS", "20"))

        self.app_base_url = os.getenv("APP_BASE_URL", "")

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_style == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_style == "header":
            headers[self.api_key_header] = self.api_key
        # "query" style is applied in _build_request instead.
        return headers

    def _build_request(
        self, payload: DigestPayload, recipient: str
    ) -> tuple[str, dict, dict, dict]:
        """Return (url, headers, json_body, query_params).

        Isolated so that adapting to the real Postpeer contract is a
        one-method change — see the module docstring.
        """
        url = f"{self.base_url}{self.send_path}"
        params: dict = {}
        if self.auth_style == "query":
            params["api_key"] = self.api_key

        body: dict = {self.field_to: recipient}
        if self.sender_id:
            body[self.field_from] = self.sender_id

        if self.template_name:
            # Template mode: the approved template owns the wording, so we pass
            # only the variable parts. The order here must match the
            # placeholder order in the approved template ({{1}}, {{2}}, {{3}}).
            top = payload.matches[0]
            body["template"] = {
                "name": self.template_name,
                "language": {"code": self.template_language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": payload.full_name or "there"},
                            {"type": "text", "text": str(len(payload.matches))},
                            {
                                "type": "text",
                                "text": f"{top.job.title} at {top.job.company}",
                            },
                        ],
                    }
                ],
            }
        else:
            body[self.field_body] = render_whatsapp_text(payload, self.app_base_url)

        return url, self._headers(), body, params

    def send(self, payload: DigestPayload, recipient: str) -> DeliveryResult:
        if not self.is_configured():
            return DeliveryResult.failed(
                self.channel, self.name, "Postpeer is not configured"
            )
        if not payload.matches:
            return DeliveryResult.failed(self.channel, self.name, "no matches to send")

        url, headers, body, params = self._build_request(payload, recipient)

        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                params=params or None,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            # Network-level failure. The dispatcher falls back to email.
            logger.warning("Postpeer request failed for %s: %s", payload.user_id, exc)
            return DeliveryResult.failed(
                self.channel, self.name, f"request failed: {exc}"
            )

        if response.status_code >= 400:
            # Truncated: provider errors can be long HTML pages, and this
            # string lands in a DB column that humans read.
            detail = response.text[:300]
            logger.warning(
                "Postpeer rejected message for %s: HTTP %s %s",
                payload.user_id,
                response.status_code,
                detail,
            )
            return DeliveryResult.failed(
                self.channel, self.name, f"HTTP {response.status_code}: {detail}"
            )

        message_id = None
        try:
            message_id = _dig(response.json(), self.response_id_path)
        except ValueError:
            # A 2xx with a non-JSON body still counts as delivered; we just
            # have no id to record.
            pass

        return DeliveryResult.ok(self.channel, self.name, message_id)
