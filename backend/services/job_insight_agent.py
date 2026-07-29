"""Job Insight Agent (Week 3 - Skill Gap task).

Where this sits in the pipeline:
    CV PDF -> CV Parser -> Candidate Profile
    Job Parser -> Job Information
    Skill Gap Analyzer -> match_score, matched_skills, missing_skills (per job)
    Matching & Ranking Engine -> ranks jobs, returns the Top 3 shortlist
    Job Insight Agent (THIS MODULE) -> strength / weakness / recommendation
        per shortlisted job, plus a UI-ready summary of all of them

This module does NOT recalculate any of the above. Given the candidate
profile and the Matching Engine's already-ranked shortlist (a list of
`MatchedJob` - see `backend/models/job_insight.py`), it asks Gemini,
once per job, for exactly three short fields (`strength`, `weakness`,
`recommendation`) and appends them to that job's existing data. It
never touches `match_score`, `matched_skills`, or `missing_skills`,
never re-ranks the shortlist, and never re-runs the Skill Gap Analyzer
or the Matching Engine.

Relationship to match_explanation_agent.py:
This module and `backend.services.match_explanation_agent` are both
"explain an already-computed match, never compute it" layers built on
the same shared Gemini plumbing (`gemini_client.call_gemini`), and
they follow the same reliability pattern (deterministic Gemini config,
retry-once-on-invalid-JSON, deterministic data-only fallback, careful
non-PII logging) by convention. They are kept as separate modules
rather than merged because they serve different UI surfaces with
different output contracts:
    - `match_explanation_agent.py`: ONE job at a time, a detailed
      5-field explanation (`MatchExplanation`), cached in an
      `AgentContext` for later follow-up chat.
    - `job_insight_agent.py` (this module): a BATCH of jobs (today,
      the Top 3), a compact 3-field annotation per job
      (`JobFitInsight`), with no caching or follow-up concept - it's a
      one-shot shortlist annotation generated right after matching.
Only the Gemini call itself is centralized
(`backend.services.gemini_client.call_gemini`); the JSON-parsing and
retry/fallback logic below is intentionally self-contained rather than
imported from `match_explanation_agent.py`, mirroring how
`gemini_matcher.py` and `match_explanation_agent.py` already each own
their own local parsing helpers instead of sharing one - the schemas
differ enough (list-of-strings fields there vs. three plain strings
here) that sharing would mean threading a generic type through both,
which is more coupling than either module needs today.

Reliability contract:
`generate_job_insight` (one job) requests the most deterministic
output Gemini supports for this call (`temperature=0.0`,
`response_mime_type="application/json"` - see `_INSIGHT_TEMPERATURE` /
`_INSIGHT_RESPONSE_MIME_TYPE`), then retries once specifically on an
invalid/unparseable/INCOMPLETE JSON response (distinct from
`gemini_client`'s own retry for transient network errors) - the total
attempt count is `_INSIGHT_MAX_ATTEMPTS`. A response
that passes schema validation is also checked for completeness -
`strength`, `weakness`, and `recommendation` must each be present and
non-empty (`_is_complete_insight`); a schema-valid but incomplete
response is treated exactly like invalid JSON, so it is never returned
and never saved into an augmented job. If parsing/validation/
completeness fails for `_INSIGHT_MAX_ATTEMPTS` attempts in a row, or
Gemini is unavailable/unconfigured, or the prompt itself can't be built
(e.g. a missing/unreadable `job_insight.md`), this degrades to a
deterministic, data-only
`JobFitInsight` built directly from that job's
`matched_skills`/`missing_skills` (never invented) - see
`_fallback_insight`. This NEVER raises for "the AI behaved badly" (or
"the prompt file is misconfigured") reasons. `generate_top_matches_insights` (the whole shortlist) simply
calls `generate_job_insight` once per job - one job's Gemini failure
never blocks or invalidates the others. `generate_job_insights` (note
the plural, batch entry point) wraps that loop and also returns the
UI-ready summary in the same call - see that function.

Logging:
Cache-free by design (no `AgentContext` here), so logging is limited
to per-job Gemini retries and fallback usage, at appropriate levels
(WARNING for invalid JSON / fallback, INFO for "Gemini unavailable").
Only `job_id` is logged - never profile content, skills, job
descriptions, or the raw Gemini response text, which could contain
personal information.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from backend.models.job_insight import JobFitInsight, JobInsight, MatchedJob
from backend.models.profile import Profile
from backend.services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

_INSIGHT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "job_insight.md"

# Generation config for the per-job insight call: temperature=0.0 for
# minimal sampling variance, response_mime_type="application/json" to
# request the SDK's native JSON output mode - both make the first-try
# JSON parse in `_try_parse_insight` succeed more often. Passed straight
# through to `gemini_client.call_gemini`'s `temperature` /
# `response_mime_type` arguments, which default to `None` (no override)
# for any caller that doesn't set them - this only affects this module's
# own calls.
_INSIGHT_TEMPERATURE = 0.0
_INSIGHT_RESPONSE_MIME_TYPE = "application/json"

# Total call attempts per job: 1 initial + 1 retry (see module docstring
# "Reliability contract"). Centralized here - previously this was only
# implicit in `generate_job_insight`'s control flow being written out
# twice. Mirrors the identical `max_attempts = 2` convention already used
# by `gemini_client.call_gemini`'s own transient-error retry loop.
_INSIGHT_MAX_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Prompt loading (cached, same pattern as gemini_matcher.py / match_explanation_agent.py)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_insight_prompt() -> str:
    """Load `backend/prompts/job_insight.md`, once, and cache it."""
    return _INSIGHT_PROMPT_PATH.read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    """Strip ```json / ``` fences some models add despite instructions."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
    return cleaned.strip()


def _build_insight_prompt(profile: Profile, matched_job: MatchedJob) -> str:
    """Assemble the job-insight prompt: system rules + read-only input data.

    The candidate profile, job info, and match result are serialized
    as-is - this function performs no computation, only formatting.
    """
    template = _load_insight_prompt()
    payload = {
        "candidate_profile": {
            "target_role": profile.target_role,
            "experience_level": profile.experience_level,
            "skills": profile.skills,
        },
        "job_information": {
            "job_id": matched_job.job.job_id,
            "title": matched_job.job.title,
            "company": matched_job.job.company,
            "required_skills": matched_job.job.required_skills,
        },
        "match_result": matched_job.match_result.to_dict(),
    }
    return f"{template}\n\n## Input\n\n{json.dumps(payload, indent=2)}\n"


def _is_complete_insight(insight: JobFitInsight) -> bool:
    """Check that `insight` actually has all three required fields
    populated - `strength`, `weakness`, and `recommendation` each a
    non-empty (post-`strip()`) string.

    `JobFitInsight`'s Pydantic schema alone isn't enough here: every
    field has a safe `""` default (see that class's docstring), so a
    Gemini response that omits a field, or sets it to `""` or
    whitespace, still passes `model_validate()`. This is the explicit
    "did Gemini actually give us all three fields" check requested on
    top of that - called from `_try_parse_insight` immediately after
    schema validation succeeds, so an incomplete response is treated
    exactly like an invalid one (never returned, never saved) - see
    that function and `generate_job_insight`'s retry-then-fallback
    behavior.
    """
    return bool(
        insight.strength.strip()
        and insight.weakness.strip()
        and insight.recommendation.strip()
    )


def _try_parse_insight(raw_text: str) -> Optional[JobFitInsight]:
    """Try to parse, validate, and completeness-check a raw Gemini
    response into a `JobFitInsight`.

    Returns `None` (never raises) on any failure - empty response,
    invalid JSON, non-object JSON, schema validation failure, or a
    schema-valid but INCOMPLETE response (a missing or empty
    `strength`/`weakness`/`recommendation` - see
    `_is_complete_insight`) - each logged individually so the specific
    cause is visible. Never logs the response/exception content itself
    - see module docstring "Logging".

    Unlike a "parse or fall back" function, this deliberately returns
    `None` instead of a fallback object, so the caller
    (`generate_job_insight`) can decide whether to retry once before
    giving up - see that function's retry-on-invalid-JSON logic. An
    incomplete result is never returned here and therefore never saved
    into an augmented job - it goes through that same retry, then
    fallback, path.
    """
    cleaned = _strip_code_fences(raw_text)

    if not cleaned:
        logger.warning("Job-insight response was empty.")
        return None

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Job-insight response was not valid JSON.")
        return None

    if not isinstance(data, dict):
        logger.warning("Job-insight response was not a JSON object.")
        return None

    try:
        insight = JobFitInsight.model_validate(data)
    except ValidationError as exc:
        # Log only the error count, never `exc`'s message text: pydantic
        # includes the actual offending field value in a ValidationError's
        # string representation, which could echo back candidate-derived
        # content from the Gemini response.
        logger.warning(
            "Job-insight response failed schema validation (%d error(s)).",
            len(exc.errors()),
        )
        return None

    if not _is_complete_insight(insight):
        logger.warning("Job-insight response was missing one or more required fields.")
        return None

    return insight


def _fallback_insight(matched_job: MatchedJob) -> JobFitInsight:
    """Deterministic, data-only insight used when Gemini is unavailable,
    unconfigured, or returns invalid JSON twice in a row (initial
    attempt + one retry - see `generate_job_insight`).

    Built ONLY from `matched_job.match_result` fields already computed
    upstream - never invents a skill or a different score.

    Guarantee: this ALWAYS returns a fully valid `JobFitInsight`
    instance with every field present and set to a non-empty string,
    never `None` or a partial/raw-JSON value.
    """
    matched_skills = matched_job.match_result.matched_skills
    missing_skills = matched_job.match_result.missing_skills

    if matched_skills:
        strength = f"Matches required skill(s): {', '.join(matched_skills)}."
    else:
        strength = "No directly matched required skills were identified for this role."

    if missing_skills:
        weakness = f"Missing required skill(s): {', '.join(missing_skills)}."
        recommendation = f"Consider developing '{missing_skills[0]}' to strengthen this match."
    else:
        weakness = "No missing required skills were identified for this role."
        recommendation = "Your matched skills already align well with this role - consider applying."

    return JobFitInsight(strength=strength, weakness=weakness, recommendation=recommendation)


def _call_gemini_for_insight(
    prompt: str, model: Optional[str], api_key: Optional[str]
) -> Optional[str]:
    """Call Gemini with this module's pinned, deterministic generation
    config (`_INSIGHT_TEMPERATURE`, `_INSIGHT_RESPONSE_MIME_TYPE`).

    Thin wrapper so every call site (initial attempt, retry) shares one
    place that pins those two settings, instead of repeating both kwargs
    at each call site. Inherits `call_gemini`'s never-raises contract.
    """
    return call_gemini(
        prompt,
        model=model,
        api_key=api_key,
        temperature=_INSIGHT_TEMPERATURE,
        response_mime_type=_INSIGHT_RESPONSE_MIME_TYPE,
    )


def generate_job_insight(
    profile: Profile,
    matched_job: MatchedJob,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> JobFitInsight:
    """Generate a strength/weakness/recommendation annotation for ONE
    already-ranked, already-scored job.

    This function NEVER recalculates `matched_job.match_result.match_score`,
    `matched_skills`, or `missing_skills` - it only asks Gemini to
    annotate them (per `backend/prompts/job_insight.md`).

    Args:
        profile: The candidate's profile (read-only context).
        matched_job: One shortlist entry - job info + its already-
            computed match result. Treated as immutable ground truth.
        model: Gemini model override (mainly for tests). Defaults to
            `GEMINI_MODEL` env var / `gemini_client.DEFAULT_MODEL`.
        api_key: Gemini API key override (mainly for tests). Defaults
            to `GEMINI_API_KEY` env var.

    Returns:
        A validated `JobFitInsight`. Falls back to a deterministic,
        data-only insight (never raises) if: the prompt can't be built
        (e.g. a missing/misconfigured prompt file), Gemini is
        unavailable/unconfigured, or Gemini returns invalid or
        incomplete JSON for `_INSIGHT_MAX_ATTEMPTS` attempts in a row
        (one initial attempt + one retry - see module docstring
        "Reliability contract"). A response that comes back `None`
        (Gemini unavailable/unconfigured) is never retried - `call_gemini`
        already exhausts its own internal retry for transient errors, so
        a `None` here means a non-transient condition (missing key, SDK
        absent) that would just return `None` again immediately.
    """
    job_id = matched_job.job.job_id  # Only identifier logged below - never profile/job content.

    try:
        prompt = _build_insight_prompt(profile, matched_job)
    except Exception:
        # Infra/config failure (e.g. job_insight.md missing or unreadable)
        # rather than "the AI behaved badly" - still degrades to the same
        # deterministic fallback instead of raising, consistent with this
        # function's documented never-raises contract.
        logger.exception("job_insight: prompt_build_failed job_id=%s action=fallback", job_id)
        return _fallback_insight(matched_job)

    for attempt in range(1, _INSIGHT_MAX_ATTEMPTS + 1):
        raw_text = _call_gemini_for_insight(prompt, model, api_key)
        if raw_text is None:
            logger.info(
                "job_insight: gemini_unavailable job_id=%s attempt=%d/%d action=fallback",
                job_id, attempt, _INSIGHT_MAX_ATTEMPTS,
            )
            return _fallback_insight(matched_job)

        insight = _try_parse_insight(raw_text)
        if insight is not None:
            return insight

        action = "retry" if attempt < _INSIGHT_MAX_ATTEMPTS else "fallback"
        logger.warning(
            "job_insight: invalid_or_incomplete_response job_id=%s attempt=%d/%d action=%s",
            job_id, attempt, _INSIGHT_MAX_ATTEMPTS, action,
        )

    return _fallback_insight(matched_job)


def build_job_insight(matched_job: MatchedJob, insight: JobFitInsight) -> JobInsight:
    """Package a `MatchedJob` + its generated `JobFitInsight` into the
    final, UI-ready `JobInsight`.

    This performs no Gemini call and no computation - a pure assembly
    step that copies every existing field from `matched_job` unchanged
    and appends the three new insight fields, exactly matching
    "preserve all existing job fields and only append the three
    required fields".

    Args:
        matched_job: The shortlist entry the insight was generated for.
        insight: The validated (or fallback) `JobFitInsight` for it.

    Returns:
        A `JobInsight` with `match_score` identical to
        `matched_job.match_result.match_score` - never recalculated.
    """
    return JobInsight(
        job_id=matched_job.job.job_id,
        title=matched_job.job.title,
        company=matched_job.job.company,
        required_skills=list(matched_job.job.required_skills),
        match_score=matched_job.match_result.match_score,
        matched_skills=list(matched_job.match_result.matched_skills),
        missing_skills=list(matched_job.match_result.missing_skills),
        strength=insight.strength,
        weakness=insight.weakness,
        recommendation=insight.recommendation,
    )


def generate_top_matches_insights(
    profile: Profile,
    matched_jobs: List[MatchedJob],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[JobInsight]:
    """Annotate every job in the Matching Engine's shortlist.

    Calls `generate_job_insight` once per entry in `matched_jobs` (in
    the order given - the Matching Engine's ranking, e.g. Top 3, is
    preserved, never re-sorted here) and packages each result via
    `build_job_insight`. One job's Gemini failure degrades only that
    job to its fallback insight (see `generate_job_insight`) - it never
    blocks or invalidates the others.

    Args:
        profile: The candidate's profile - shared context for every job.
        matched_jobs: The Matching Engine's already-ranked shortlist
            (today, the Top 3). Never re-ranked, re-scored, or
            re-matched here.
        model: Gemini model override, forwarded to `generate_job_insight`.
        api_key: Gemini API key override, forwarded to `generate_job_insight`.

    Returns:
        One `JobInsight` per entry in `matched_jobs`, same order,
        each preserving that job's existing fields plus the three
        appended insight fields.
    """
    return [
        build_job_insight(
            matched_job,
            generate_job_insight(profile, matched_job, model=model, api_key=api_key),
        )
        for matched_job in matched_jobs
    ]


def generate_job_insights(
    profile: Profile,
    matched_jobs: List[MatchedJob],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[List[JobInsight], Dict[str, Any]]:
    """Process the entire Top-3 (or however many) shortlist in one call:
    generate an insight for every job, then build the UI-ready summary -
    returning BOTH.

    This is the primary batch entry point for the Week 3 flow:
        generate_job_insights(top_jobs)
            -> generate_job_insight(job1)
            -> generate_job_insight(job2)
            -> generate_job_insight(job3)
    It is a thin composition of `generate_top_matches_insights` (the
    per-job loop) and `build_ui_summary` (the formatting step) - no new
    business logic, just the combined return shape most callers
    processing the whole shortlist in one step want. (`generate_top_matches_insights`
    and `generate_top_matches_summary` remain available separately for
    callers that only need one half of this.)

    Args:
        profile: The candidate's profile - shared context for every job.
        matched_jobs: The Matching Engine's already-ranked shortlist
            (today, the Top 3). Never re-ranked, re-scored, or
            re-matched here.
        model: Gemini model override, forwarded to `generate_job_insight`.
        api_key: Gemini API key override, forwarded to `generate_job_insight`.

    Returns:
        A `(augmented_jobs, ui_summary)` tuple:
            - `augmented_jobs`: one `JobInsight` per entry in
              `matched_jobs`, same order - see
              `generate_top_matches_insights`.
            - `ui_summary`: the same dict shape as `build_ui_summary`.
    """
    augmented_jobs = generate_top_matches_insights(
        profile, matched_jobs, model=model, api_key=api_key
    )
    ui_summary = build_ui_summary(augmented_jobs)
    return augmented_jobs, ui_summary


# ---------------------------------------------------------------------------
# UI-ready summary
#
# Pure formatting - no Gemini call, no computation. Turns a list of
# `JobInsight` into a shape a frontend can render directly: each job's
# strength/weakness/recommendation as three labeled "sections", so the UI
# can map over `sections` without hardcoding field names.
# ---------------------------------------------------------------------------


def build_ui_summary(insights: List[JobInsight]) -> Dict[str, Any]:
    """Build a clean, UI-ready summary of all annotated jobs.

    Args:
        insights: The `JobInsight` list to summarize, typically from
            `generate_top_matches_insights`. Order is preserved.

    Returns:
        A JSON-serializable dict:
        ```json
        {
          "job_count": 3,
          "jobs": [
            {
              "job_id": "...", "title": "...", "company": "...",
              "match_score": 82,
              "matched_skills": [...], "missing_skills": [...],
              "sections": [
                {"label": "Strength", "content": "..."},
                {"label": "Weakness", "content": "..."},
                {"label": "Recommendation", "content": "..."}
              ]
            },
            ...
          ]
        }
        ```
        `sections` is what makes this "UI-ready": a frontend can render
        each job's three blocks by iterating `sections` directly,
        without needing to know the underlying field names.
    """
    return {
        "job_count": len(insights),
        "jobs": [
            {
                "job_id": insight.job_id,
                "title": insight.title,
                "company": insight.company,
                "match_score": insight.match_score,
                "matched_skills": insight.matched_skills,
                "missing_skills": insight.missing_skills,
                "sections": [
                    {"label": "Strength", "content": insight.strength},
                    {"label": "Weakness", "content": insight.weakness},
                    {"label": "Recommendation", "content": insight.recommendation},
                ],
            }
            for insight in insights
        ],
    }


def render_ui_summary_markdown(insights: List[JobInsight]) -> str:
    """Render the same summary as `build_ui_summary`, as plain Markdown.

    Convenience alternative to the structured dict - useful for a quick
    preview, an export, or sharing outside the UI (e.g. a chat message).
    Not the primary contract (that's `build_ui_summary`); both read
    from the same `JobInsight` list and never disagree with each other.

    Args:
        insights: The `JobInsight` list to render. Order is preserved.

    Returns:
        A Markdown string with one section per job.
    """
    if not insights:
        return "No matched jobs to summarize."

    blocks = []
    for insight in insights:
        company_suffix = f" - {insight.company}" if insight.company else ""
        blocks.append(
            f"### {insight.title}{company_suffix} (Match score: {insight.match_score})\n\n"
            f"**Strength:** {insight.strength}\n\n"
            f"**Weakness:** {insight.weakness}\n\n"
            f"**Recommendation:** {insight.recommendation}\n"
        )
    return "\n".join(blocks)


def generate_top_matches_summary(
    profile: Profile,
    matched_jobs: List[MatchedJob],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience entry point: annotate the shortlist and build its
    UI-ready summary in one call.

    Equivalent to `build_ui_summary(generate_top_matches_insights(...))` -
    provided because this is the shape a route handler (or any single
    call site) typically wants directly. See those two functions for
    the underlying contract and reliability/logging guarantees.

    Args:
        profile: The candidate's profile.
        matched_jobs: The Matching Engine's already-ranked shortlist.
        model: Gemini model override, forwarded through.
        api_key: Gemini API key override, forwarded through.

    Returns:
        The same dict shape as `build_ui_summary`.
    """
    insights = generate_top_matches_insights(profile, matched_jobs, model=model, api_key=api_key)
    return build_ui_summary(insights)
