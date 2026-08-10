"""The gate in front of the routes that send messages or read across users.

This is a stopgap, and it is worth being precise about what it is a stopgap
*for*. The correct fix is that `user_id` comes from an authenticated session
rather than from the URL path, so that asking for someone else's digest is not
expressible. This service has no session concept — `user_id` is always
`"default"` — so that fix cannot be written here. Until it can, a shared secret
at least means the dangerous routes are not open to the public internet.

What is dangerous, and why:

* `POST /notifications/dispatch` runs the digest for every user on record. The
  once-per-day idempotency caps the blast radius at one message per user, which
  is real mitigation, but "one unsolicited message to your entire user base"
  is still not something to leave reachable.
* `POST /notifications/send-test/{user_id}` sends a message to any named user,
  over email or WhatsApp, from our sender identity and on our infrastructure.
* `GET /notifications/preview/{user_id}` returns another person's ranked job
  matches, which is a fair proxy for their CV and their career intentions.
* `GET /notifications/logs` returns delivery history across every user.
* `PUT /notifications/settings/{user_id}/profile` overwrites the profile
  someone else's digest is scored against.

## The rule

`NOTIFICATIONS_ADMIN_TOKEN` set → every gated route requires a matching
`X-Admin-Token` header.

`NOTIFICATIONS_ADMIN_TOKEN` unset → the gated routes are served **only while no
provider can actually transmit**, i.e. the zero-credential console mode that
`docs/notifications.md` tells you to demo with. Configure a real SMTP host or
Postpeer key without setting a token and the gated routes return 503 rather
than quietly becoming a public send button.

Failing closed on configuration is the whole point. An env var that defaults to
"no auth" protects nobody, because the deployment that forgets to set it is
exactly the deployment that needed it.

The residual gap, stated plainly: an instance deployed in console mode still
serves `preview` and `logs` to anyone. Real per-user auth is the only fix for
that, and it belongs to whoever owns auth for this service.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

from backend.features.notifications.providers import build_provider_chain

#: Shared secret. Blank/unset means "console demo only" — see the module docs.
ADMIN_TOKEN_ENV = "NOTIFICATIONS_ADMIN_TOKEN"

#: Header the secret travels in.
ADMIN_TOKEN_HEADER = "X-Admin-Token"


def configured_admin_token() -> str:
    """The shared secret, or "" when none is configured."""
    return os.getenv(ADMIN_TOKEN_ENV, "").strip()


def can_transmit() -> bool:
    """True when at least one provider would put a real message on the wire.

    Deliberately *not* `is_configured()`: that returns True for SMTP in console
    mode, whose entire job is to print the digest instead of sending it. The
    question this gate asks is "can a request here reach a real person", and
    console mode cannot.
    """
    for provider in build_provider_chain():
        if provider.is_configured() and not getattr(provider, "is_console", False):
            return True
    return False


def require_admin_token(
    x_admin_token: Optional[str] = Header(default=None, alias=ADMIN_TOKEN_HEADER),
) -> None:
    """FastAPI dependency: allow the request, or raise 401/503.

    Returns None on success — nothing downstream needs an identity from this,
    because a shared secret does not carry one. That is precisely its
    limitation, and why the docstring above calls it a stopgap.
    """
    token = configured_admin_token()

    if not token:
        if can_transmit():
            raise HTTPException(
                status_code=503,
                detail=(
                    f"This endpoint is disabled: a delivery provider is "
                    f"configured but {ADMIN_TOKEN_ENV} is not set, so the "
                    f"route would be an unauthenticated way to send real "
                    f"messages. Set {ADMIN_TOKEN_ENV} and send it as "
                    f"{ADMIN_TOKEN_HEADER}."
                ),
            )
        # Console mode: nothing can leave the machine, so the demo documented
        # in docs/notifications.md keeps working with no configuration.
        return

    # compare_digest, not ==, so a wrong token cannot be recovered a character
    # at a time from response timing.
    #
    # Compared as bytes rather than str: compare_digest rejects a str holding
    # any non-ASCII character with TypeError, and Starlette decodes headers as
    # latin-1, so a header containing "é" would turn a 401 into a 500.
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token.encode("utf-8"), token.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail=f"Missing or invalid {ADMIN_TOKEN_HEADER}.",
            headers={"WWW-Authenticate": ADMIN_TOKEN_HEADER},
        )
