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
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "litellm"
DEFAULT_LITELLM_MODEL = "kimi-k2.5"

# LiteLLM rejects an unbounded completion on some models, and the gateway's own
# examples set it, so a default is sent unless the caller overrides it.
DEFAULT_MAX_TOKENS = 2000

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


def _is_transient(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _call_litellm(
    prompt: str,
    model: Optional[str],
    api_key: Optional[str],
    temperature: Optional[float],
    response_mime_type: Optional[str],
    max_tokens: Optional[int],
) -> Optional[str]:
    key = api_key or os.getenv("LITELLM_API_KEY")
    base_url = os.getenv("LITELLM_BASE_URL")
    if not key:
        logger.info("LITELLM_API_KEY not set; skipping LLM call.")
        return None
    if not base_url:
        logger.info("LITELLM_BASE_URL not set; skipping LLM call.")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping LLM call.")
        return None

    # The gateway exposes an OpenAI-compatible surface under /v1, which the SDK
    # appends itself, so the configured base URL is used as given.
    client = OpenAI(base_url=base_url, api_key=key)
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
    # unsupported-parameter error is retried once without it: callers all parse
    # defensively and strip code fences anyway.
    attempts = [dict(request)]
    if response_mime_type == "application/json":
        attempts.insert(
            0, dict(request, response_format={"type": "json_object"})
        )

    last_exc = None
    for body in attempts:
        for attempt in range(2):
            try:
                response = client.chat.completions.create(**body)
                return (response.choices[0].message.content or "").strip()
            except Exception as exc:  # noqa: BLE001 - must degrade, not raise
                last_exc = exc
                if attempt == 0 and _is_transient(exc):
                    logger.warning(
                        "Transient LiteLLM error on %s; retrying once: %s",
                        resolved, exc,
                    )
                    continue
                break
        if "response_format" in body:
            logger.warning(
                "LiteLLM rejected response_format on %s; retrying without it.",
                resolved,
            )

    logger.warning("LiteLLM call failed on %s: %s", resolved, last_exc)
    return None


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
    provider = active_provider()

    if provider == "gemini":
        # Imported here so a LiteLLM-only deployment does not need the Gemini
        # SDK present just to import this module.
        from backend.services.gemini_client import call_gemini_direct

        return call_gemini_direct(
            prompt,
            model=model,
            api_key=api_key,
            temperature=temperature,
            response_mime_type=response_mime_type,
        )

    if provider != "litellm":
        logger.warning(
            "Unknown AI_PROVIDER %r; falling back to %s.", provider,
            DEFAULT_PROVIDER,
        )

    return _call_litellm(
        prompt, model, api_key, temperature, response_mime_type, max_tokens
    )
