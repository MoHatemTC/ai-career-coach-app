"""Shared, low-level Gemini API client.

Purpose:
Multiple services in this codebase need to call Gemini (semantic
skill matching in `gemini_matcher.py`, and the Match Explanation
Agent in `match_explanation_agent.py`, with more likely later - e.g.
a follow-up chatbot). Each of those has its OWN prompt and its OWN
response schema, but they all need the exact same plumbing to
actually reach the model: resolve which model/key to use, construct
the SDK client, call it, and retry once on a transient failure.

This module is that one shared plumbing layer. It knows nothing about
skills, match scores, or explanations - it only knows how to send a
prompt string to Gemini and get a raw text response back (or `None`).
Every other Gemini-calling service in this repo should import
`call_gemini()` from here rather than writing its own
`genai.Client(...)` + retry loop.

Configuration:
  - `GEMINI_MODEL` env var selects the model, defaulting to
    "gemini-2.5-pro" if unset.
  - `GEMINI_API_KEY` env var supplies the API key.
Both can be overridden by passing `model=` / `api_key=` explicitly
(mainly for tests / DI).

Generation config (temperature / response_mime_type):
`call_gemini()` also accepts optional `temperature` and
`response_mime_type` arguments so a caller that needs deterministic,
machine-parseable output (e.g. the Match Explanation Agent, which
parses the response as JSON) can request it - `temperature=0.0` for
minimal sampling variance, `response_mime_type="application/json"`
for the SDK's native JSON output mode. Both default to `None`
("don't ask for anything specific, use the SDK's own defaults"), so
existing callers that don't pass them (e.g. `gemini_matcher.py`'s
semantic-matching pass) see byte-for-byte identical behavior to
before this option existed - no `config` is even sent to the SDK
unless at least one of these is provided. See `_build_generation_config`.

Reliability contract:
`call_gemini()` NEVER raises for provider-side failures (missing key,
missing SDK, network error, timeout, malformed response). It returns
`None` in every one of those cases, so callers can always fall back to
a deterministic result - never propagate a Gemini outage as a user-
facing error. Building the optional generation config follows the same
contract: if it fails for any reason (SDK too old, unexpected kwarg),
the call proceeds without it rather than raising - see
`_build_generation_config`.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-pro"

# Transient-failure signals worth one automatic retry (rate limiting,
# temporary unavailability, timeouts/connection hiccups). Anything else
# (auth errors, malformed requests, etc.) is not transient and falls
# back immediately - see `_is_transient_error` / `call_gemini`.
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_MESSAGE_MARKERS = (
    "429",
    "rate limit",
    "resource exhausted",
    "unavailable",
    "timeout",
    "timed out",
    "connection",
)


def resolve_model(model: Optional[str] = None) -> str:
    """Resolve which Gemini model to use.

    Precedence: explicit `model` argument > `GEMINI_MODEL` env var >
    `DEFAULT_MODEL`.
    """
    return model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def _is_transient_error(exc: Exception) -> bool:
    """Best-effort check for whether `exc` looks like a transient
    provider-side failure (rate limiting, temporary unavailability,
    timeout/connection issue) worth one retry, vs. something that will
    fail again immediately (bad auth, malformed request, etc.).

    Deliberately duck-typed rather than tied to specific google-genai
    exception classes, since SDK exception hierarchies change across
    versions - this only inspects a `status_code`/`code` attribute if
    present, and otherwise falls back to matching common substrings in
    the exception message.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS_CODES:
        return True

    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MESSAGE_MARKERS)


def _build_generation_config(
    temperature: Optional[float],
    response_mime_type: Optional[str],
) -> Optional[object]:
    """Build a `google.genai.types.GenerateContentConfig`, or `None`.

    Returns `None` (meaning "send no config at all, same as before this
    option existed") when both arguments are `None` - this is what keeps
    existing callers that never pass `temperature`/`response_mime_type`
    completely unaffected.

    Never raises: if the SDK's `types` module is unavailable, or
    constructing `GenerateContentConfig` fails for any other reason
    (e.g. an older SDK version with a different signature), this logs a
    warning and returns `None` so the caller falls back to the SDK's
    own default sampling/output behavior rather than failing the whole
    request over a determinism nice-to-have.
    """
    if temperature is None and response_mime_type is None:
        return None

    try:
        from google.genai import types

        config_kwargs = {}
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if response_mime_type is not None:
            config_kwargs["response_mime_type"] = response_mime_type
        return types.GenerateContentConfig(**config_kwargs)
    except Exception as exc:  # noqa: BLE001 - a determinism nice-to-have must never break the call.
        logger.warning(
            "Could not build Gemini generation config (%s); proceeding without it.",
            exc,
        )
        return None


def call_gemini(
    prompt: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    response_mime_type: Optional[str] = None,
) -> Optional[str]:
    """Send `prompt` to Gemini and return the raw response text.

    This is the ONLY function in the codebase that should construct a
    `google.genai.Client` or call `generate_content`. Any service that
    needs Gemini (semantic matching, match explanation, follow-up
    chat, ...) calls this instead of writing its own client code.

    Args:
        prompt: Full prompt text to send (system instructions + data,
            already assembled by the caller - this function has no
            opinion on prompt content).
        model: Gemini model id. Defaults to the `GEMINI_MODEL` env var,
            falling back to `DEFAULT_MODEL` if that's unset too.
        api_key: Overrides the `GEMINI_API_KEY` env var, mainly for tests.
        temperature: Optional sampling temperature (e.g. `0.0` for the
            most deterministic output the model supports). `None`
            (the default) sends no temperature override at all - the
            SDK/model's own default applies, exactly as before this
            argument existed.
        response_mime_type: Optional response MIME type (e.g.
            `"application/json"` to request the SDK's native JSON
            output mode). `None` (the default) sends no override,
            exactly as before this argument existed.

    Returns:
        The raw response text, or `None` if the API key is missing,
        the `google-genai` SDK isn't installed, or the call fails
        (after one retry for transient errors). Never raises.
    """
    resolved_model = resolve_model(model)

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("GEMINI_API_KEY not set; skipping Gemini call.")
        return None

    try:
        from google import genai  # Official Google GenAI SDK (not the deprecated one).
    except ImportError:
        logger.warning("google-genai package not installed; skipping Gemini call.")
        return None

    generation_config = _build_generation_config(temperature, response_mime_type)

    # At most one retry (2 attempts total), and only for signals that
    # look transient (rate limiting, temporary unavailability, timeouts).
    # Anything else - or a second failure - returns None immediately.
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            client = genai.Client(api_key=key)
            request_kwargs = {"model": resolved_model, "contents": prompt}
            # Only send `config` at all when one was actually requested,
            # so a caller that passes neither `temperature` nor
            # `response_mime_type` (e.g. gemini_matcher.py today) issues
            # the exact same `generate_content(model=..., contents=...)`
            # call as before this option existed.
            if generation_config is not None:
                request_kwargs["config"] = generation_config
            response = client.models.generate_content(**request_kwargs)
            return getattr(response, "text", None) or ""
        except Exception as exc:  # noqa: BLE001 - any SDK/network failure must degrade, not raise.
            if attempt < max_attempts and _is_transient_error(exc):
                logger.warning(
                    "Transient Gemini error on attempt %d/%d (%s); retrying once.",
                    attempt,
                    max_attempts,
                    exc,
                )
                continue
            logger.exception("Gemini call failed; returning None.")
            return None

    return None  # Unreachable in practice; keeps type-checkers happy.
