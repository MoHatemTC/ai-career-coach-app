"""Provider-agnostic LLM entry point.

One place that decides which provider a completion goes to, so switching does
not mean editing every caller. `AI_PROVIDER` picks it, which is what that
variable was declared for in `.env.example` from the start; nothing read it
until now.

- `AI_PROVIDER=litellm` (default): the Sprints LiteLLM gateway, via the OpenAI
  SDK, since LiteLLM speaks the OpenAI wire protocol.
- `AI_PROVIDER=gemini`: Gemini direct, through `gemini_client`.

The gateway is the default because the direct Gemini keys are heavily rate
limited: a single pipeline run makes three explanation calls plus a ranking
call, which is enough to hit the ceiling during a demo.

THE CONTRACT
------------
`complete()` NEVER raises for provider-side failures. It returns `None` on a
missing key, a missing SDK, a network error, a timeout or a malformed response,
so every caller can fall back to something deterministic. This mirrors
`gemini_client.call_gemini` exactly, so either can back the other.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "litellm"

# The group email advertises kimi-k2.5, but the team key is not entitled to it:
# the gateway answers 403 "This team can only access models=['gemini/*']".
# Verified against the live gateway — of the 72 ids it lists, the text models
# that actually complete are the gemini/-prefixed ones, and an id without that
# prefix is refused even when the listing shows it. gemini/gemini-pro-latest is
# an alias, so it does not rot the way a pinned version does.
DEFAULT_LITELLM_MODEL = "gemini/gemini-pro-latest"

# LiteLLM rejects an unbounded completion on some models, and the gateway's own
# examples set it, so a default is sent unless the caller overrides it.
DEFAULT_MAX_TOKENS = 2000

# The OpenAI SDK's own default is measured in minutes, so a wrong base URL made
# the whole request hang rather than failing usefully. A pipeline run makes four
# of these calls, so the ceiling has to be something a person will wait through.
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))

# Retried once. Anything else (bad auth, malformed request) fails the same way
# twice, so retrying only adds latency.
_TRANSIENT_MARKERS = (
    "429", "rate limit", "resource exhausted", "unavailable", "timeout",
    "timed out", "connection", "502", "503", "504",
)


def active_provider() -> str:
    """Which provider completions go to. Read at call time so .env applies."""
    return (os.getenv("AI_PROVIDER") or DEFAULT_PROVIDER).strip().lower()


def litellm_model(model: Optional[str] = None) -> str:
    """Precedence: explicit argument > DEFAULT_MODEL env var > built-in."""
    return model or os.getenv("DEFAULT_MODEL") or DEFAULT_LITELLM_MODEL


# A model that does not implement JSON mode says so in one of these ways.
_RESPONSE_FORMAT_MARKERS = (
    "response_format", "response format", "json_object", "json mode",
)


def normalise_base_url(base_url: str) -> str:
    """Ensure the base URL points at the OpenAI-compatible `/v1` surface.

    The OpenAI SDK does NOT append `/v1`: it uses `base_url` verbatim and adds
    only `/chat/completions`. Its own default is `https://api.openai.com/v1`,
    with the version already in it.

    The gateway's welcome message gives the base as
    `https://learner-os.sprints.ai/litellm` while its example curl posts to
    `.../litellm/v1/chat/completions`. Pasting the advertised base URL therefore
    sends requests to `/litellm/chat/completions`, which does not answer, and
    the call hangs until it times out rather than returning a 404. Appending it
    here means the value from the email works as given.
    """
    trimmed = (base_url or "").rstrip("/")
    if not trimmed:
        return trimmed
    # Respect an explicit version segment; only add one when it is absent.
    last = trimmed.rsplit("/", 1)[-1]
    if last.startswith("v") and last[1:].isdigit():
        return trimmed
    return f"{trimmed}/v1"


def _is_transient(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _rejects_response_format(exc: Exception) -> bool:
    """Is this failure specifically about JSON mode being unsupported?"""
    text = str(exc).lower()
    return any(marker in text for marker in _RESPONSE_FORMAT_MARKERS)


def _call_litellm(
    prompt: str,
    model: Optional[str],
    api_key: Optional[str],
    temperature: Optional[float],
    response_mime_type: Optional[str],
    max_tokens: Optional[int],
) -> Tuple[Optional[str], Optional[str]]:
    key = api_key or os.getenv("LITELLM_API_KEY")
    base_url = os.getenv("LITELLM_BASE_URL")
    if not key:
        logger.info("LITELLM_API_KEY not set; skipping LLM call.")
        return None, "LITELLM_API_KEY is not set in .env"
    if not base_url:
        logger.info("LITELLM_BASE_URL not set; skipping LLM call.")
        return None, "LITELLM_BASE_URL is not set in .env"

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping LLM call.")
        return None, "the openai package is not installed"

    client = OpenAI(
        base_url=normalise_base_url(base_url), api_key=key,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=0,  # retries are handled here, with our own conditions
    )
    resolved = litellm_model(model)

    request = {
        "model": resolved,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens or DEFAULT_MAX_TOKENS,
    }
    if temperature is not None:
        request["temperature"] = temperature

    # JSON mode is requested when asked for, but not every model behind the
    # gateway supports response_format. Rather than fail the call, an
    # unsupported-parameter error drops it and retries once: callers all parse
    # defensively and strip code fences anyway.
    if response_mime_type == "application/json":
        request["response_format"] = {"type": "json_object"}

    last_exc = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(**request)
            return (response.choices[0].message.content or "").strip(), None
        except Exception as exc:  # noqa: BLE001 - must degrade, not raise
            last_exc = exc

            # Only drop response_format when the failure is actually about
            # response_format. Dropping it on any error meant a timeout ran the
            # whole retry loop twice, so one unreachable gateway cost four
            # requests and four timeouts before returning.
            if "response_format" in request and _rejects_response_format(exc):
                logger.warning(
                    "LiteLLM rejected response_format on %s; retrying without "
                    "it.", resolved,
                )
                request.pop("response_format")
                continue

            if attempt == 0 and _is_transient(exc):
                logger.warning(
                    "Transient LiteLLM error on %s; retrying once: %s",
                    resolved, exc,
                )
                continue
            break

    logger.warning("LiteLLM call failed on %s: %s", resolved, last_exc)
    # The gateway's own words, with the model named. A team key restricted to
    # one provider answers 403 "team not allowed to access model", which says
    # precisely what is wrong — and used to be discarded, leaving the caller to
    # blame the URL and the key, both of which were fine.
    return None, f"the gateway rejected model {resolved!r}: {last_exc}"


def complete_with_reason(
    prompt: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    response_mime_type: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """`complete()`, but also returns why it failed. Reason is None on success.

    Exists because the reason used to be thrown away. A team key restricted to
    one provider answers 403 "team not allowed to access model", naming the
    model — and the caller, seeing only None, told the user to check the URL and
    the key, which were both correct. The reason is a sentence fragment meant to
    be embedded in a caller's message, not a full sentence of its own.
    """
    provider = active_provider()

    if provider == "gemini":
        # Imported here so a LiteLLM-only deployment does not need the Gemini
        # SDK present just to import this module.
        from backend.services.gemini_client import call_gemini_direct

        text = call_gemini_direct(
            prompt,
            model=model,
            api_key=api_key,
            temperature=temperature,
            response_mime_type=response_mime_type,
        )
        # call_gemini_direct predates this and reports nothing but None, so the
        # best available reason names where to look rather than guessing.
        if text is None:
            return None, "the Gemini call returned nothing; check GEMINI_API_KEY and GEMINI_MODEL"
        return text, None

    if provider != "litellm":
        logger.warning(
            "Unknown AI_PROVIDER %r; falling back to %s.", provider,
            DEFAULT_PROVIDER,
        )

    return _call_litellm(
        prompt, model, api_key, temperature, response_mime_type, max_tokens
    )


def complete(
    prompt: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    response_mime_type: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """Send `prompt` to the configured provider and return the text, or None.

    Never raises. `response_mime_type="application/json"` requests JSON mode
    where the provider supports it; callers must still parse defensively,
    because a model can ignore it.
    """
    return complete_with_reason(
        prompt, model, api_key, temperature, response_mime_type, max_tokens
    )[0]
