"""Gemini-powered semantic skill matcher.

Purpose (PRD Section 7.6 / Section 8 - AI requirements):
The deterministic baseline in `backend/services/skill_gap.py` only
catches exact matches and known aliases (`skill_taxonomy.py`). It has
no way to know that "FastAPI" satisfies a "REST API Development"
requirement, or that "PyTorch" satisfies "Deep Learning" - those are
semantic equivalences, not spelling variants.

This module adds an OPTIONAL second pass that asks Gemini to classify
semantic equivalence for whatever skills the deterministic baseline
could not already resolve. Per the project brief and
`docs/architecture.md` ("AI Prompt Flow"):

    1. A service loads a prompt from `backend/prompts/`.
    2. The service sends profile/job data to the AI client.
    3. The AI client returns a structured response.
    4. The service validates the response before returning it.

This module is ONLY that AI client + validation step (points 2-4). It
does not:
    - parse CVs or job postings,
    - calculate match scores, priorities, or recommendations,
    - decide what counts as a "gap" - `skill_gap.py` still owns all of
      that. This module's only job is: given two lists of already
      -normalized skill names, classify how they relate.

Shared Gemini client:
The low-level "call Gemini and get text back, with retry" plumbing
lives in `backend.services.gemini_client` (`call_gemini()`), shared
with any other Gemini-calling service in this repo (e.g. the Match
Explanation Agent). This module owns only what's specific to semantic
skill matching: the prompt (`backend/prompts/skill_gap.md`) and the
`SemanticMatchResult` response schema.

Reliability contract:
This module NEVER raises for "the AI behaved badly" reasons (bad JSON,
schema mismatch, timeout, missing API key, missing SDK). Every one of
those degrades to `empty_result()`, a deterministic, all-empty
`SemanticMatchResult`, so `skill_gap.py` can always safely fall back to
the taxonomy-only baseline. It only raises for programmer errors (e.g.
calling with unexpected types), same as any other Python code.

Provider interface:
`skill_gap.py` depends only on the `SemanticMatcher` abstract interface
(`match(candidate_skills, required_skills) -> SemanticMatchResult`),
never on Gemini-specific names. `GeminiMatcher` is this module's
concrete implementation. A future provider (OpenAI, Claude, a local
model, ...) is a new `SemanticMatcher` subclass here - no changes
needed in `skill_gap.py`.

Configuration:
  - `GEMINI_MODEL` env var selects the model, defaulting to
    "gemini-2.5-pro" if unset.
  - `GEMINI_API_KEY` env var supplies the API key.
Both can also be passed explicitly (mainly for tests / DI).

Reliability extras:
  - The prompt file is read from disk once per process and cached
    (`_load_prompt_template`), not re-read per request.
  - A single transient failure (HTTP 429/5xx, timeout, connection
    issue) triggers exactly one retry before falling back - never an
    unbounded retry loop.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "skill_gap.md"


# ---------------------------------------------------------------------------
# Response schema
#
# This is the contract between "whatever Gemini said" and the rest of the
# codebase. `skill_gap.py` NEVER touches a raw Gemini response - only this
# validated model. Every field required by comparisons downstream has an
# explicit default, so a partially-populated response still validates
# instead of raising.
# ---------------------------------------------------------------------------


class MatchedSkillPair(BaseModel):
    """One required skill Gemini judged as semantically satisfied."""

    required_skill: str
    candidate_skill: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class PartialSkillPair(BaseModel):
    """One required skill Gemini judged as only partially satisfied."""

    required_skill: str
    candidate_skill: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class MissingSkillEntry(BaseModel):
    """One required skill Gemini found no meaningful coverage for."""

    required_skill: str
    reason: str = ""


class SemanticMatchResult(BaseModel):
    """Validated shape of a Gemini semantic-matching response.

    This is the ONLY thing `skill_gap.py` is allowed to consume from
    this module. All three lists default to empty so a malformed or
    partial response still produces a *valid, inert* result rather
    than an exception - see `empty_result()`.
    """

    matched_skills: List[MatchedSkillPair] = Field(default_factory=list)
    partially_matched: List[PartialSkillPair] = Field(default_factory=list)
    missing_skills: List[MissingSkillEntry] = Field(default_factory=list)


def empty_result() -> SemanticMatchResult:
    """Deterministic fallback: "Gemini found nothing extra."

    Returned whenever the API call fails, times out, isn't configured,
    or returns something that doesn't validate against
    `SemanticMatchResult`. Callers (`skill_gap.py`) treat this exactly
    like "no semantic matches found" and fall back completely to the
    deterministic taxonomy comparison they already computed - Gemini
    only ever augments that baseline, never blocks or replaces it.
    """
    return SemanticMatchResult()


class SemanticMatcher(ABC):
    """Provider-agnostic interface for semantic skill matching.

    `skill_gap.py` depends ONLY on this interface, never on Gemini
    specifics - so adding a future provider (OpenAI, Claude, a local
    model, ...) means writing a new subclass here, with zero changes
    to `skill_gap.py`.
    """

    @abstractmethod
    def match(self, candidate_skills: List[str], required_skills: List[str]) -> "SemanticMatchResult":
        """Classify `required_skills` against `candidate_skills`.

        Args:
            candidate_skills: Candidate's canonical/normalized skills.
            required_skills: Canonical required skills the caller
                couldn't already resolve deterministically.

        Returns:
            A validated `SemanticMatchResult`. Implementations must
            never raise for provider-side failures (bad response,
            network error, etc.) - degrade to `empty_result()`
            instead, so callers can always fall back safely.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    """Load the prompt body from `backend/prompts/skill_gap.md`, once.

    Per CONTRIBUTING.md "Prompt Policy": prompts live in
    `backend/prompts/`, never hard-coded inside Python files.

    Cached with `lru_cache` so repeated calls (one per request) don't
    hit disk each time - the prompt file doesn't change at runtime.
    `lru_cache` is thread-safe: concurrent callers either share the
    cached result or, in the rare case of a first-call race, each
    independently reads the (identical) file - never a partial read or
    a corrupted cache entry.

    Call `_load_prompt_template.cache_clear()` (mainly useful in tests)
    to force a re-read, e.g. after monkeypatching `_PROMPT_PATH`.
    """
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_prompt(held_skills: List[str], required_skills: List[str]) -> str:
    template = _load_prompt_template()
    return (
        f"{template}\n\n"
        "## Input\n\n"
        f"Candidate's normalized skills: {json.dumps(held_skills)}\n"
        f"Required skills NOT already resolved by exact/alias matching: "
        f"{json.dumps(required_skills)}\n"
    )


# ---------------------------------------------------------------------------
# Response parsing / validation
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Strip ```json / ``` fences some models add despite instructions."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
    return cleaned.strip()


def _is_transient_error(exc: Exception) -> bool:
    """Re-exported from `gemini_client` for backward compatibility.

    The retry logic itself now lives in `backend.services.gemini_client`
    (shared with any other Gemini-calling service) - this module no
    longer calls it directly, but keeps the name importable here since
    existing tests/tools may reference `gemini_matcher._is_transient_error`.
    """
    from backend.services.gemini_client import _is_transient_error as _impl

    return _impl(exc)


def parse_and_validate(raw_text: str) -> SemanticMatchResult:
    """Parse + validate a raw model response into a `SemanticMatchResult`.

    Never raises: any parsing or validation failure logs a warning and
    returns `empty_result()` instead, so a malformed/incomplete Gemini
    response degrades gracefully rather than breaking the gap analysis.
    """
    cleaned = _strip_code_fences(raw_text)

    if not cleaned:
        logger.warning("Gemini semantic-match returned an empty response; using fallback.")
        return empty_result()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Gemini semantic-match response was not valid JSON; using fallback.")
        return empty_result()

    if not isinstance(data, dict):
        logger.warning("Gemini semantic-match response was not a JSON object; using fallback.")
        return empty_result()

    try:
        return SemanticMatchResult.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "Gemini semantic-match response failed schema validation (%s); using fallback.",
            exc,
        )
        return empty_result()


# ---------------------------------------------------------------------------
# Gemini client call
# ---------------------------------------------------------------------------


def gemini_semantic_match(
    held_skills: List[str],
    required_skills: List[str],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> SemanticMatchResult:
    """Ask Gemini to semantically match `required_skills` against `held_skills`.

    Args:
        held_skills: Candidate's canonical/normalized skills.
        required_skills: Canonical required skills that the
            deterministic taxonomy baseline could NOT already match -
            this function is only ever asked about the leftovers.
        model: Gemini model id. Defaults to the `GEMINI_MODEL` env var,
            falling back to "gemini-2.5-pro" if that's unset too.
        api_key: Overrides `GEMINI_API_KEY` env var, mainly for tests.

    Returns:
        A validated `SemanticMatchResult`. Falls back to
        `empty_result()` (never raises) if the API key is missing, the
        SDK isn't installed, the call fails, or the response doesn't
        validate - see module docstring "Reliability contract".
    """
    if not required_skills:
        return empty_result()

    prompt = _build_prompt(held_skills, required_skills)
    raw_text = call_gemini(prompt, model=model, api_key=api_key)

    if raw_text is None:
        # call_gemini() already logged the specific reason (missing
        # key, missing SDK, or a failed/retried call).
        return empty_result()

    return parse_and_validate(raw_text)


# ---------------------------------------------------------------------------
# SemanticMatcher implementation
# ---------------------------------------------------------------------------


class GeminiMatcher(SemanticMatcher):
    """`SemanticMatcher` implementation backed by Gemini.

    A thin adapter over `gemini_semantic_match()` (which stays a plain,
    directly-testable function) so `skill_gap.py` can depend on the
    `SemanticMatcher` interface instead of importing Gemini-specific
    functions. Adding a future provider (e.g. `OpenAIMatcher`,
    `ClaudeMatcher`, a local-model matcher) means writing a new
    `SemanticMatcher` subclass here - `skill_gap.py` needs no changes.
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """Args mirror `gemini_semantic_match`: both default to env vars
        (`GEMINI_MODEL`, `GEMINI_API_KEY`) resolved at call time if omitted.
        """
        self._model = model
        self._api_key = api_key

    def match(self, candidate_skills: List[str], required_skills: List[str]) -> SemanticMatchResult:
        return gemini_semantic_match(
            held_skills=candidate_skills,
            required_skills=required_skills,
            model=self._model,
            api_key=self._api_key,
        )
