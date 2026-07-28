"""Match Explanation Agent.

Purpose:
The pipeline up to this point already produces a final, deterministic
match result:
    CV PDF -> CV Parser -> Candidate Profile
    Job Parser -> Job Information
    Skill Gap Analyzer -> match_score, matched_skills, missing_skills

This module does NOT recalculate any of that. It is strictly an
explanation layer: given the candidate profile, job information, and
the already-computed match result, it asks Gemini to explain what the
result means - in the required JSON shape - and never touches the
score or skill lists themselves.

Why the LLM is never responsible for the score:
The score is a deterministic, reproducible fact computed by the
matching engine - it must mean the same thing every time it's shown.
An LLM call is neither deterministic nor reproducible across calls,
so letting it touch the score would make the score itself unreliable.
This module therefore treats `match_result.match_score` (and
`matched_skills`/`missing_skills`) as fixed inputs: Gemini is asked to
explain them in prose, never to compute, restate as a different
number, or contradict them. Every prompt (`match_explanation.md`,
`match_followup.md`) says this explicitly, and the response schema
(`MatchExplanation`) has no field the LLM could use to override the
score even if it tried.

Two entry points:
  - `generate_match_explanation` / `get_or_create_explanation`: produce
    (or reuse) the initial explanation, packaged into an `AgentContext`
    (`backend/models/agent_context.py`) for later reuse.
  - `answer_followup_question`: answers a follow-up question using an
    existing `AgentContext`, without re-running the Skill Gap Analyzer,
    the matching engine, or the explanation prompt again. Flow:
    `load_context()` -> `build_prompt()` -> Gemini -> answer.

Why the explanation is cached, and why validated before reuse:
Generating an explanation costs a Gemini call (latency + money) and
its wording isn't guaranteed to be stable across calls. Once generated
for a given (candidate_id, job_id) pair, it's treated as a stable fact
and reused via a `ContextStore` (see `backend/models/agent_context.py`
for why that's an abstraction, not a concrete in-memory dependency).
But a cache entry could in principle be stale, corrupted, or belong to
the wrong pair (e.g. a bug upstream, or - once a real distributed
store like Redis is in place - a partially-written record). So a cache
hit is only trusted after `_is_valid_cached_context` confirms it
actually matches the requested pair, has a real explanation and score,
and was written with a supported `context_version` (see
`backend.models.agent_context.CURRENT_CONTEXT_VERSION`); anything else
is treated as a cache miss and regenerated - see
`get_or_create_explanation`.

Dependency injection vs. the legacy global store:
The module-level functions (`get_or_create_explanation`, `load_context`,
etc.) accept an optional `store: ContextStore` and fall back to
`backend.models.agent_context.default_store` (a process-local
singleton) when omitted - kept only for backward compatibility with
existing call sites. New code should prefer `MatchExplanationAgent`
(below), which takes its `ContextStore` through its constructor and
never touches the global default - no hidden global state to reason
about, and a `RedisContextStore` (or per-request store, or test double)
can be injected explicitly.

Shared Gemini client:
Like `backend/services/gemini_matcher.py`, this module calls Gemini
through the shared `backend.services.gemini_client.call_gemini()` -
it does not construct its own `google.genai.Client` or duplicate the
retry logic.

Reliability contract:
This module NEVER raises for "the AI behaved badly" reasons (bad JSON,
schema mismatch, timeout, missing API key, missing SDK).
`generate_match_explanation` requests the most deterministic output
Gemini supports for this call (`temperature=0.0`,
`response_mime_type="application/json"` - see `_EXPLANATION_TEMPERATURE`
/ `_EXPLANATION_RESPONSE_MIME_TYPE`, passed through to
`gemini_client.call_gemini`), then retries once specifically on an
invalid/unparseable JSON response (distinct from `gemini_client`'s own
retry for transient network errors). A response that DOES parse and
validate is then checked once more for tone consistency with the score
(`_validated_or_fallback` / `_is_explanation_consistent_with_score`) -
a clear contradiction (e.g. a high score described as "a poor fit") is
treated the same as an invalid response. If parsing/validation fails
twice in a row, or a validated response fails the tone check, this
degrades to a deterministic, data-only `MatchExplanation` built
directly from the match result (never invented) - this fallback is
ALWAYS a fully valid `MatchExplanation` (every field present, correct
type), never a plain string or partial JSON; see
`_fallback_explanation`. None of this ever retries or regenerates
specifically because of a tone mismatch - it degrades straight to the
fallback, per this feature's explicit design.
`answer_followup_question` also requests `temperature=0.0` (but not
`response_mime_type="application/json"` - its answer is intentionally
plain text, see `match_followup.md`), and degrades to a generic
fallback string if Gemini is unavailable.
Nothing in this module ever contradicts or recomputes the underlying
score.

Logging:
Cache hits/misses, invalid cache entries, Gemini retries, tone-
inconsistent responses, and fallback usage are all logged at
appropriate levels (INFO for normal cache flow, WARNING for invalid/
inconsistent/fallback situations) using only identifiers
(`candidate_id`/`job_id`), the score itself, and counts/booleans -
never profile content, skills, explanation text, or the candidate's
follow-up question, which could contain personal information.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.models.agent_context import (
    AgentContext,
    ContextStore,
    CURRENT_CONTEXT_VERSION,
    default_store,
)
from backend.models.job import JobInfo
from backend.models.match_result import MatchResult
from backend.models.profile import Profile
from backend.services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

_EXPLANATION_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "match_explanation.md"
)
_FOLLOWUP_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "match_followup.md"
)

_FALLBACK_FOLLOWUP_ANSWER = (
    "I can't reach the explanation service right now, but you can review the "
    "strengths and gaps already listed in your match explanation above."
)

# Generation config for the explanation-generation call (see
# `generate_match_explanation`): temperature=0.0 for minimal sampling
# variance, response_mime_type="application/json" to request the SDK's
# native JSON output mode. Both are passed straight through to
# `backend.services.gemini_client.call_gemini`'s `temperature` /
# `response_mime_type` arguments, which default to `None` (no override)
# for any caller that doesn't set them - this only affects this module's
# own calls. The goal is purely reliability: making the first-try JSON
# parse in `_try_parse_explanation` succeed more often, not a prompt or
# business-logic change.
_EXPLANATION_TEMPERATURE = 0.0
_EXPLANATION_RESPONSE_MIME_TYPE = "application/json"

# The follow-up answer is intentionally plain text, not JSON (see
# `match_followup.md`), so only `temperature` is set for it -
# `response_mime_type="application/json"` would fight the prompt's own
# "respond in plain text" instruction.
_FOLLOWUP_TEMPERATURE = 0.0


# ---------------------------------------------------------------------------
# Response schema
#
# This is the contract between "whatever Gemini said" and the rest of the
# codebase. Nothing downstream ever touches a raw Gemini response - only
# this validated model.
# ---------------------------------------------------------------------------


class MatchExplanation(BaseModel):
    """Validated shape of the Match Explanation Agent's output.

    Every field has a safe default so a partially-populated response
    still validates instead of raising - see `_parse_and_validate`.
    """

    overall_alignment_summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    gaps_or_missing_requirements: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


def _fallback_explanation(match_result: MatchResult) -> MatchExplanation:
    """Deterministic, data-only explanation used when Gemini is
    unavailable, unconfigured, or returns invalid JSON twice in a row
    (initial attempt + one retry - see `generate_match_explanation`).

    Built ONLY from `match_result` fields already computed upstream -
    never invents a skill or a different score.

    Guarantee: this ALWAYS returns a fully valid `MatchExplanation`
    instance with every field present and correctly typed
    (`overall_alignment_summary: str`, and `strengths` /
    `gaps_or_missing_requirements` / `recommendations` / `next_steps`
    all `list[str]`, each possibly empty but never missing or `None`).
    It never returns a plain string, a partial dict, or raw JSON text -
    callers can rely on this being exactly as structurally sound as a
    successfully-parsed Gemini response.
    """
    if match_result.missing_skills:
        recommendations = [f"Consider developing '{skill}'." for skill in match_result.missing_skills]
        next_steps = ["Review the missing skills above before applying, if possible."]
    else:
        recommendations = []
        next_steps = ["Your matched skills already align well with this role - consider applying."]

    return MatchExplanation(
        overall_alignment_summary=(
            f"Match score is {match_result.match_score}. "
            f"{len(match_result.matched_skills)} matched skill(s) and "
            f"{len(match_result.missing_skills)} missing skill(s) were found."
        ),
        strengths=list(match_result.matched_skills),
        gaps_or_missing_requirements=list(match_result.missing_skills),
        recommendations=recommendations,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# Prompt loading (cached, same pattern as gemini_matcher.py)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_explanation_prompt() -> str:
    """Load `backend/prompts/match_explanation.md`, once, and cache it."""
    return _EXPLANATION_PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_followup_prompt() -> str:
    """Load `backend/prompts/match_followup.md`, once, and cache it."""
    return _FOLLOWUP_PROMPT_PATH.read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    """Strip ```json / ``` fences some models add despite instructions."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
    return cleaned.strip()


def _build_explanation_prompt(profile: Profile, job: JobInfo, match_result: MatchResult) -> str:
    """Assemble the explanation prompt: system rules + read-only input data.

    The candidate profile, job info, and match result are serialized
    as-is - this function performs no computation, only formatting.
    """
    template = _load_explanation_prompt()
    payload = {
        "candidate_profile": {
            "target_role": profile.target_role,
            "experience_level": profile.experience_level,
            "skills": profile.skills,
        },
        "job_information": {
            "job_id": job.job_id,
            "title": job.title,
            "company": job.company,
            "required_skills": job.required_skills,
        },
        "match_result": match_result.to_dict(),
    }
    return f"{template}\n\n## Input\n\n{json.dumps(payload, indent=2)}\n"


def _try_parse_explanation(raw_text: str) -> Optional[MatchExplanation]:
    """Try to parse + validate a raw Gemini response into a `MatchExplanation`.

    Returns `None` (never raises) on any failure - empty response,
    invalid JSON, non-object JSON, or schema validation failure - each
    logged individually so the specific cause is visible.

    Unlike a "parse or fall back" function, this deliberately returns
    `None` instead of a fallback object, so the caller
    (`generate_match_explanation`) can decide whether to retry once
    before giving up - see that function's retry-on-invalid-JSON logic.
    """
    cleaned = _strip_code_fences(raw_text)

    if not cleaned:
        logger.warning("Match-explanation response was empty.")
        return None

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Match-explanation response was not valid JSON: %s", exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Match-explanation response was not a JSON object.")
        return None

    try:
        return MatchExplanation.model_validate(data)
    except ValidationError as exc:
        # Log only the error count, never `exc`'s message text: pydantic
        # includes the actual offending field value in a ValidationError's
        # string representation, which could echo back candidate-derived
        # content from the Gemini response - see module docstring "Logging".
        logger.warning(
            "Match-explanation response failed schema validation (%d error(s)).",
            len(exc.errors()),
        )
        return None


# ---------------------------------------------------------------------------
# Explanation generation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Explanation consistency validation
#
# A lightweight, deterministic sanity check applied AFTER a Gemini response
# has already been parsed and schema-validated (`_try_parse_explanation`),
# and BEFORE it is returned from `generate_match_explanation` - i.e. before
# it can ever reach `build_agent_context` / be saved into an `AgentContext`.
#
# It does NOT recompute, adjust, or second-guess `match_score`,
# `matched_skills`, or `missing_skills` in any way, and it does NOT trigger
# regeneration. It only asks one narrow question: does the TONE of
# `overall_alignment_summary` clearly contradict the score bucket it was
# supposed to explain (e.g. a high score described as "a poor fit")? If so,
# the wording - not the score - is what's untrustworthy, so the response is
# discarded in favor of the existing deterministic fallback
# (`_fallback_explanation`), exactly like an invalid-JSON response.
#
# Thresholds are intentionally coarse and the phrase lists intentionally
# short and literal (substring checks, not sentiment analysis): this is
# meant to catch obvious, unambiguous mismatches only. A summary that
# doesn't contain any of these phrases is treated as consistent - false
# negatives (missing a subtle mismatch) are preferred over false positives
# (rejecting a legitimate, nuanced summary and paying for a wasted Gemini
# call for no reason).
# ---------------------------------------------------------------------------

_HIGH_SCORE_THRESHOLD = 75.0
_LOW_SCORE_THRESHOLD = 40.0

# Phrases that would clearly contradict a HIGH-scoring match (i.e. describe
# a poor/mismatched fit) if they appeared in its summary.
_NEGATIVE_FIT_PHRASES = (
    "poor fit",
    "poor match",
    "bad fit",
    "not a good fit",
    "not a strong fit",
    "weak fit",
    "weak match",
    "significant mismatch",
    "not suitable",
    "not recommended",
    "unlikely to be a fit",
)

# Phrases that would clearly contradict a LOW-scoring match (i.e. overclaim
# an excellent fit) if they appeared in its summary.
_POSITIVE_FIT_PHRASES = (
    "excellent fit",
    "excellent match",
    "perfect fit",
    "perfect match",
    "ideal candidate",
    "outstanding fit",
    "strong fit",
    "great fit",
    "great match",
)


def _is_explanation_consistent_with_score(
    explanation: MatchExplanation, match_score: float
) -> bool:
    """Lightweight tone check: does `explanation` clearly contradict `match_score`?

    This NEVER recalculates or second-guesses `match_score` - it only
    checks whether `overall_alignment_summary`'s wording is an obvious
    tonal mismatch for the score bucket it's meant to describe:
        - High score (`>= _HIGH_SCORE_THRESHOLD`): must not use clearly
          negative/poor-fit language (`_NEGATIVE_FIT_PHRASES`).
        - Low score (`< _LOW_SCORE_THRESHOLD`): must not use clearly
          overclaiming/excellent-fit language (`_POSITIVE_FIT_PHRASES`).
        - Medium score (everything in between): no check is applied - a
          genuinely balanced summary can legitimately lean mildly
          positive or mildly negative, so this band is deliberately
          lenient to avoid false positives.

    Args:
        explanation: The parsed, schema-valid `MatchExplanation` to check.
        match_score: The existing, already-computed match score. Read
            only - never modified here or anywhere else in this module.

    Returns:
        `True` if no clear contradiction was found (including for every
        medium-band score, where no check applies at all). `False` only
        on an unambiguous mismatch against the phrase lists above.
    """
    summary = explanation.overall_alignment_summary.lower()

    if match_score >= _HIGH_SCORE_THRESHOLD:
        return not any(phrase in summary for phrase in _NEGATIVE_FIT_PHRASES)

    if match_score < _LOW_SCORE_THRESHOLD:
        return not any(phrase in summary for phrase in _POSITIVE_FIT_PHRASES)

    return True


def _validated_or_fallback(
    explanation: MatchExplanation,
    match_result: MatchResult,
    candidate_id: str,
    job_id: str,
) -> MatchExplanation:
    """Return `explanation` if consistent with the score, else the fallback.

    This is the single checkpoint `generate_match_explanation` routes
    every successfully-parsed response through - on the initial attempt
    and on the retry alike - immediately before returning, so nothing
    tonally inconsistent with `match_result.match_score` can ever reach
    `build_agent_context` or be saved by a `ContextStore`. Does not
    retry or regenerate on a tone mismatch - it degrades straight to
    `_fallback_explanation`, per this feature's explicit design.

    Args:
        explanation: The parsed, schema-valid `MatchExplanation` to check.
        match_result: The already-computed match result - supplies both
            `match_score` (for the tone check) and the data used to build
            the fallback if needed. Never modified.
        candidate_id: Candidate identifier, for logging only.
        job_id: Job identifier, for logging only.

    Returns:
        `explanation` unchanged if it passes the consistency check,
        otherwise `_fallback_explanation(match_result)`.
    """
    if _is_explanation_consistent_with_score(explanation, match_result.match_score):
        return explanation

    # Only identifiers and the (already non-sensitive) score are logged -
    # never the explanation text itself, consistent with this module's
    # logging discipline (see module docstring "Logging").
    logger.warning(
        "match_explanation: inconsistent_tone candidate_id=%s job_id=%s "
        "match_score=%s action=fallback",
        candidate_id,
        job_id,
        match_result.match_score,
    )
    return _fallback_explanation(match_result)


def generate_match_explanation(
    profile: Profile,
    job: JobInfo,
    match_result: MatchResult,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> MatchExplanation:
    """Generate an AI explanation for an ALREADY-COMPUTED match result.

    This function NEVER recalculates `match_result.match_score`,
    `matched_skills`, or `missing_skills` - it only asks Gemini to
    explain them (per `backend/prompts/match_explanation.md`), and
    validates the response before returning it: first structurally
    (`_try_parse_explanation`, JSON + schema), then for tone consistency
    with the score (`_validated_or_fallback`) - see module docstring
    "Reliability contract".

    Args:
        profile: The candidate's profile (read-only context).
        job: The job's information (read-only context).
        match_result: The final, already-computed match result to
            explain. Treated as immutable ground truth.
        model: Gemini model override (mainly for tests). Defaults to
            `GEMINI_MODEL` env var / "gemini-2.5-pro".
        api_key: Gemini API key override (mainly for tests). Defaults
            to `GEMINI_API_KEY` env var.

    Returns:
        A validated `MatchExplanation`. Falls back to a deterministic,
        data-only explanation (never raises) if Gemini is unavailable,
        unconfigured, returns invalid JSON twice in a row (one initial
        attempt + one retry), or returns a response whose tone clearly
        contradicts the given score (see module docstring "Reliability
        contract").
    """
    prompt = _build_explanation_prompt(profile, job, match_result)
    # Only identifiers are logged below - never profile skills, job
    # details, the raw prompt, or the raw Gemini response text, which
    # could contain personal information.
    candidate_id, job_id = profile.user_id, job.job_id

    raw_text = call_gemini(
        prompt,
        model=model,
        api_key=api_key,
        temperature=_EXPLANATION_TEMPERATURE,
        response_mime_type=_EXPLANATION_RESPONSE_MIME_TYPE,
    )
    if raw_text is None:
        logger.info(
            "match_explanation: gemini_unavailable candidate_id=%s job_id=%s "
            "action=fallback",
            candidate_id,
            job_id,
        )
        return _fallback_explanation(match_result)

    explanation = _try_parse_explanation(raw_text)
    if explanation is not None:
        return _validated_or_fallback(explanation, match_result, candidate_id, job_id)

    # Invalid JSON on the first attempt: retry once before falling back.
    # This is separate from gemini_client's own retry (which only covers
    # transient network errors, not content the model itself got wrong).
    logger.warning(
        "match_explanation: invalid_json candidate_id=%s job_id=%s action=retry",
        candidate_id,
        job_id,
    )
    retry_raw_text = call_gemini(
        prompt,
        model=model,
        api_key=api_key,
        temperature=_EXPLANATION_TEMPERATURE,
        response_mime_type=_EXPLANATION_RESPONSE_MIME_TYPE,
    )
    if retry_raw_text is None:
        logger.info(
            "match_explanation: gemini_unavailable_on_retry candidate_id=%s "
            "job_id=%s action=fallback",
            candidate_id,
            job_id,
        )
        return _fallback_explanation(match_result)

    explanation = _try_parse_explanation(retry_raw_text)
    if explanation is not None:
        return _validated_or_fallback(explanation, match_result, candidate_id, job_id)

    logger.warning(
        "match_explanation: invalid_json_after_retry candidate_id=%s job_id=%s "
        "action=fallback",
        candidate_id,
        job_id,
    )
    return _fallback_explanation(match_result)


def build_agent_context(
    candidate_id: str,
    job_id: str,
    match_result: MatchResult,
    explanation: MatchExplanation,
) -> AgentContext:
    """Package a generated explanation + its inputs into a reusable `AgentContext`.

    This performs no Gemini call and no computation - it's a pure
    assembly step, kept separate from `generate_match_explanation` so
    callers that already have both pieces (e.g. after re-hydrating an
    explanation from storage) can build a context without regenerating
    anything.
    """
    return AgentContext(
        candidate_id=candidate_id,
        job_id=job_id,
        match_score=match_result.match_score,
        matched_skills=list(match_result.matched_skills),
        missing_skills=list(match_result.missing_skills),
        explanation=explanation.model_dump(),
    )


def _is_valid_cached_context(
    context: AgentContext, candidate_id: str, job_id: str
) -> bool:
    """Validate a cache hit before trusting it, rather than assuming any
    stored `AgentContext` is automatically safe to reuse.

    Why this check exists: a cache entry could in principle be stale,
    corrupted, or mismatched (e.g. a store-implementation bug, or a
    partially-written record once a real distributed store like Redis
    is in place) - reusing it blindly could silently show a candidate
    someone else's explanation, or an explanation with no actual
    content. This is deliberately conservative: any of these failing
    means the caller should regenerate rather than guess.

    Checks:
        - `context.candidate_id` matches the requested `candidate_id`.
        - `context.job_id` matches the requested `job_id`.
        - `context.match_score` is present (not `None`).
        - `context.explanation` is present and non-empty.
        - `context.matched_skills` is present (not `None`).
        - `context.missing_skills` is present (not `None`).
        - `context.context_version` is a version this code supports
          (currently: exactly `CURRENT_CONTEXT_VERSION`). An older or
          newer/unrecognized version is treated as invalid rather than
          risking misinterpreting fields that may have changed meaning
          across schema versions - see
          `backend.models.agent_context.CURRENT_CONTEXT_VERSION`.

    Note: this only validates the cache entry's *shape* - whether it
    matches the CURRENT match result (e.g. after a candidate uploads a
    new CV, or the same candidate/job pair is re-matched with fresh
    data) is a separate check - see `_context_matches_match_result`,
    used by `get_or_create_explanation`.

    Returns:
        True only if all checks pass.
    """
    if context.candidate_id != candidate_id:
        logger.warning(
            "match_explanation: cache_invalid reason=candidate_id_mismatch "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return False

    if context.job_id != job_id:
        logger.warning(
            "match_explanation: cache_invalid reason=job_id_mismatch "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return False

    if context.context_version != CURRENT_CONTEXT_VERSION:
        logger.warning(
            "match_explanation: cache_invalid reason=unsupported_context_version "
            "candidate_id=%s job_id=%s cached_version=%s supported_version=%s",
            candidate_id,
            job_id,
            context.context_version,
            CURRENT_CONTEXT_VERSION,
        )
        return False

    if context.match_score is None:
        logger.warning(
            "match_explanation: cache_invalid reason=missing_match_score "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return False

    if not context.explanation:
        logger.warning(
            "match_explanation: cache_invalid reason=missing_explanation "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return False

    if context.matched_skills is None:
        logger.warning(
            "match_explanation: cache_invalid reason=missing_matched_skills "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return False

    if context.missing_skills is None:
        logger.warning(
            "match_explanation: cache_invalid reason=missing_missing_skills "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return False

    return True


def _context_matches_match_result(context: AgentContext, match_result: MatchResult) -> bool:
    """Check whether a cached context still reflects the CURRENT match result.

    A cache is keyed only by `(candidate_id, job_id)`, but the
    underlying data behind those ids can change without the ids
    themselves changing - most notably, a candidate re-uploading a new
    CV for the same account, or a session being re-run against fresh
    job data for the same job id. In either case the previously cached
    explanation describes a match result that no longer exists and
    must not be reused, even though the cache key still matches.

    This compares the cached `match_score` / `matched_skills` /
    `missing_skills` against the freshly-supplied `match_result` (the
    one the caller just computed from the current profile/job data).
    A mismatch means "the underlying data changed" -> treat as a cache
    miss and regenerate, exactly like `_is_valid_cached_context` failing.
    """
    return (
        context.match_score == match_result.match_score
        and list(context.matched_skills) == list(match_result.matched_skills)
        and list(context.missing_skills) == list(match_result.missing_skills)
    )


def get_or_create_explanation(
    candidate_id: str,
    job_id: str,
    profile: Profile,
    job: JobInfo,
    match_result: MatchResult,
    store: Optional[ContextStore] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AgentContext:
    """Return the cached `AgentContext` for this pair, generating it only if absent or invalid.

    This is the entry point that guarantees Gemini is called only when
    truly necessary. It calls `generate_match_explanation` (i.e. calls
    Gemini) in exactly these cases, and no others:
        1. No cached context exists for `(candidate_id, job_id)` (cache miss).
        2. A cached context exists but fails shape validation - missing
           ids, score, explanation, or skill lists (see
           `_is_valid_cached_context`).
        3. A cached context exists and is well-formed, but no longer
           matches the freshly-supplied `match_result` (see
           `_context_matches_match_result`) - e.g. the candidate
           uploaded a different CV, or selected a different job whose
           data changed under the same `job_id`.
    In every other case - a valid cache hit whose match result still
    matches - the cached context is returned immediately and Gemini is
    never called.

    Args:
        candidate_id: Candidate identifier (context cache key part 1).
        job_id: Job identifier (context cache key part 2).
        profile: Candidate profile - only used if generation is needed.
        job: Job information - only used if generation is needed.
        match_result: The CURRENT, already-computed match result (from
            the latest CV/job data) - used both to detect a stale cache
            (case 3 above) and, if generation is needed, as the
            explanation's input.
        store: `ContextStore` implementation to use (e.g.
            `InMemoryContextStore`, or a future `RedisContextStore`).
            Defaults to the shared process-local `default_store`.
        model: Gemini model override, forwarded to
            `generate_match_explanation` on a cache miss.
        api_key: Gemini API key override, forwarded to
            `generate_match_explanation` on a cache miss.

    Returns:
        The cached (and valid, and current) or newly-generated `AgentContext`.
    """
    active_store = store if store is not None else default_store

    cached = active_store.load(candidate_id, job_id)
    if cached is None:
        logger.info(
            "match_explanation: cache_miss reason=not_found candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
    elif not _is_valid_cached_context(cached, candidate_id, job_id):
        # _is_valid_cached_context already logged the specific reason.
        pass
    elif not _context_matches_match_result(cached, match_result):
        logger.info(
            "match_explanation: cache_miss reason=stale_match_result "
            "candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
    else:
        logger.info(
            "match_explanation: cache_hit candidate_id=%s job_id=%s",
            candidate_id,
            job_id,
        )
        return cached

    explanation = generate_match_explanation(
        profile, job, match_result, model=model, api_key=api_key
    )
    context = build_agent_context(candidate_id, job_id, match_result, explanation)
    active_store.save(context)
    return context


def invalidate_context(
    candidate_id: str,
    job_id: str,
    store: Optional[ContextStore] = None,
) -> None:
    """Explicitly discard any cached explanation for this pair.

    Intended for the cases where the caller already knows the cached
    context can no longer be trusted before even computing a new
    `match_result` - most notably, a candidate uploading a brand new
    CV (invalidating every cached context for that `candidate_id`
    across jobs would be the caller's responsibility, calling this once
    per affected `job_id`) or explicitly starting a new matching
    session. A no-op if nothing was cached.

    Note: `get_or_create_explanation` already detects and regenerates a
    stale cache on its own (see its docstring, case 3) even without
    this being called first - this function exists for callers that
    want to proactively clear a cache entry (e.g. right after a new CV
    upload, before any explanation is requested again).
    """
    active_store = store if store is not None else default_store
    active_store.delete(candidate_id, job_id)


def load_context(
    candidate_id: str,
    job_id: str,
    store: Optional[ContextStore] = None,
) -> Optional[AgentContext]:
    """Load a previously generated `AgentContext`, or `None` if not found.

    First step of the follow-up flow:
    `load_context()` -> `build_prompt()` -> Gemini -> answer.
    This is a pure lookup - it never triggers Skill Gap analysis, the
    matching engine, or explanation generation. (Unlike
    `get_or_create_explanation`, this does not validate the cached
    context - a caller that gets `None` back should treat it as "no
    context yet" and fall back to `get_or_create_explanation` if it
    wants one generated.)
    """
    active_store = store if store is not None else default_store
    return active_store.load(candidate_id, job_id)


def _build_followup_prompt(context: AgentContext, user_question: str) -> str:
    """Assemble the follow-up prompt from the cached context + the question.

    No re-computation happens here - `context` already carries the
    final score, skill lists, and prior explanation.
    """
    template = _load_followup_prompt()
    payload = {
        "match_score": context.match_score,
        "matched_skills": context.matched_skills,
        "missing_skills": context.missing_skills,
        "explanation": context.explanation,
        "user_question": user_question,
    }
    return f"{template}\n\n## Context\n\n{json.dumps(payload, indent=2)}\n"


def answer_followup_question(
    context: AgentContext,
    user_question: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Answer a follow-up question using an existing `AgentContext`.

    Flow: `load_context()` (by the caller, before this) -> `build_prompt`
    (this function's internal `_build_followup_prompt`) -> Gemini ->
    answer (returned here). This function NEVER re-runs Skill Gap
    analysis or the matching engine - it only reuses `context`, which
    already carries the final score and skill lists.

    Args:
        context: A previously generated `AgentContext` (from
            `load_context()` or `get_or_create_explanation()`).
        user_question: The candidate's follow-up question.
        model: Gemini model override (mainly for tests).
        api_key: Gemini API key override (mainly for tests).

    Returns:
        A plain-text answer. Falls back to a generic, non-committal
        message (never raises, never contradicts the existing score)
        if Gemini is unavailable.
    """
    prompt = _build_followup_prompt(context, user_question)
    raw_text = call_gemini(
        prompt, model=model, api_key=api_key, temperature=_FOLLOWUP_TEMPERATURE
    )

    if raw_text is None or not raw_text.strip():
        # Never log user_question or explanation content here - only
        # identifiers, consistent with the rest of this module's logging.
        logger.info(
            "match_explanation: followup_fallback candidate_id=%s job_id=%s",
            context.candidate_id,
            context.job_id,
        )
        return _FALLBACK_FOLLOWUP_ANSWER

    return raw_text.strip()


# ---------------------------------------------------------------------------
# Dependency-injected agent (preferred entry point for new code)
#
# Why this class exists: the module-level functions above default to the
# `default_store` global singleton when no `store` is passed, kept only
# for backward compatibility (see module docstring "Dependency injection
# vs. the legacy global store"). `MatchExplanationAgent` avoids that
# global entirely - its `ContextStore` is provided once, explicitly, at
# construction time, and every method uses it. This is what makes
# swapping in a `RedisContextStore` (or a per-request/test-only store)
# a one-line change at the call site, with no shared mutable global to
# reason about or accidentally leak state through between requests/tests.
# ---------------------------------------------------------------------------


class MatchExplanationAgent:
    """Match Explanation Agent with an explicitly injected `ContextStore`.

    This is a thin wrapper around the module-level functions
    (`get_or_create_explanation`, `load_context`, `answer_followup_question`,
    `invalidate_context`) - it contains no additional logic of its own,
    only forwards to them with `self._store` instead of a global default.
    The module-level functions remain available and unchanged for
    backward compatibility; this class is the recommended entry point
    for new code that wants explicit dependency injection.

    Example:
        store = InMemoryContextStore()  # or a future RedisContextStore()
        agent = MatchExplanationAgent(store=store)
        context = agent.get_or_create_explanation(
            candidate_id, job_id, profile, job, match_result
        )
        answer = agent.answer_followup_question(context, "Why am I missing X?")
    """

    def __init__(
        self,
        store: ContextStore,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Args:
            store: The `ContextStore` this agent will use for every
                operation. Required (no default) - this is the
                dependency-injection point; there is no implicit
                fallback to a global store.
            model: Gemini model override applied to every Gemini call
                this agent makes. Defaults to the `GEMINI_MODEL` env
                var / "gemini-2.5-pro" if omitted.
            api_key: Gemini API key override applied to every Gemini
                call this agent makes. Defaults to the `GEMINI_API_KEY`
                env var if omitted.
        """
        self._store = store
        self._model = model
        self._api_key = api_key

    def get_or_create_explanation(
        self,
        candidate_id: str,
        job_id: str,
        profile: Profile,
        job: JobInfo,
        match_result: MatchResult,
    ) -> AgentContext:
        """See module-level `get_or_create_explanation` - identical
        behavior, using this agent's injected store/model/api_key."""
        return get_or_create_explanation(
            candidate_id,
            job_id,
            profile,
            job,
            match_result,
            store=self._store,
            model=self._model,
            api_key=self._api_key,
        )

    def load_context(self, candidate_id: str, job_id: str) -> Optional[AgentContext]:
        """See module-level `load_context` - identical behavior, using
        this agent's injected store."""
        return load_context(candidate_id, job_id, store=self._store)

    def answer_followup_question(self, context: AgentContext, user_question: str) -> str:
        """See module-level `answer_followup_question` - identical
        behavior, using this agent's injected model/api_key. Does not
        need the store: `context` already carries everything needed."""
        return answer_followup_question(
            context, user_question, model=self._model, api_key=self._api_key
        )

    def invalidate_context(self, candidate_id: str, job_id: str) -> None:
        """See module-level `invalidate_context` - identical behavior,
        using this agent's injected store."""
        invalidate_context(candidate_id, job_id, store=self._store)
