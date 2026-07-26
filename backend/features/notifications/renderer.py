"""Turns a `DigestPayload` into channel-specific message bodies.

Kept out of the providers so that "what the message says" can be reviewed and
changed without touching "how the message is transmitted".
"""

from __future__ import annotations

import functools
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.features.notifications.schema import DigestPayload

TEMPLATE_DIR = Path(__file__).parent / "templates"


@functools.lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        # Autoescape HTML only. The .txt templates carry WhatsApp markup and
        # must not have their characters escaped.
        autoescape=select_autoescape(enabled_extensions=("html",), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _context(payload: DigestPayload, app_base_url: str) -> dict:
    return {
        "payload": payload,
        "matches": payload.matches,
        "full_name": payload.full_name or "there",
        "generated_at": payload.generated_at,
        "settings_url": f"{app_base_url.rstrip('/')}/settings" if app_base_url else "",
    }


def render_email_subject(payload: DigestPayload) -> str:
    count = len(payload.matches)
    if count == 1:
        return f"1 new job match: {payload.matches[0].job.title}"
    return f"Your top {count} job matches today"


def render_email_html(payload: DigestPayload, app_base_url: str = "") -> str:
    return _environment().get_template("digest_email.html").render(
        **_context(payload, app_base_url)
    )


def render_email_text(payload: DigestPayload, app_base_url: str = "") -> str:
    """Plain-text alternative part.

    Not optional: a multipart/alternative email without a text part is a
    well-known spam-filter signal, and the digest is the whole feature.
    """
    return _environment().get_template("digest_email.txt").render(
        **_context(payload, app_base_url)
    )


def render_whatsapp_text(payload: DigestPayload, app_base_url: str = "") -> str:
    return _environment().get_template("digest_whatsapp.txt").render(
        **_context(payload, app_base_url)
    )
