"""Adapter between the existing matching pipeline and the digest.

Design rule for this file: **do not reimplement scoring.** The score must come
from code the app already uses, so a digest can never disagree with what the
user sees on screen. Everything here is selection, translation, and filtering
around that.

Two paths, and only ever one of them per run
--------------------------------------------
1. **Pipeline** (`services/matching_pipeline.run_match_pipeline`) — Qdrant
   retrieval, LLM re-ranking, then the Match Explanation Agent. This is what
   `POST /matching/pipeline` runs, so it is what the app's own match list
   shows, and it is the only path that can fill in `reason`.

2. **Scorer fallback** (`features/matching/scorer.calculate_match_score`) —
   cosine similarity over every posting in SQLite. Used only when the pipeline
   raises or returns nothing, which is what happens when Qdrant is down, locked
   by another process, or empty. `POST /matching/rank-jobs` degrades exactly
   the same way.

The two are never mixed inside one digest. They produce numbers on the same
0-100 scale but not from the same method, and a message whose three rows were
scored by two different systems is a message whose ranking means nothing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.features.notifications.schema import TopJobMatch
from backend.features.notifications.settings_service import DigestRecipient
from backend.models.db_models import (
    JobPostingORM,
    NotificationLogORM,
    orm_to_job_posting,
)
from backend.models.job import JobPosting

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 3

# Retrieval width handed to the pipeline. Wider than DEFAULT_TOP_N on purpose:
# the re-ranker narrows to its own shortlist, and de-duplication then removes
# anything the user already saw, so a run that retrieved only three would
# usually deliver fewer than three.
PIPELINE_TOP_K = 10

# The scorer path encodes every candidate, so cost is linear in the pool and
# this runs for every user on every tick. Capping to the most recent postings
# bounds a run; freshness is what a *daily* digest is about anyway.
FALLBACK_CANDIDATE_LIMIT = 200

# How far back to look when suppressing repeats (PRD 7.9).
DEFAULT_DEDUPE_WINDOW_DAYS = 7

# The re-ranker reports fit on 0-1; match_score is 0-100. Converted once, here,
# so nothing downstream has to know which scale a number arrived on. Same
# constant and same reason as FIT_SCORE_SCALE in services/matching_pipeline.py.
FIT_SCORE_SCALE = 100.0


def _clamp_score(value: float) -> float:
    """Force a score into the 0-100 range `TopJobMatch` declares.

    Both sources can leave it. `calculate_match_score` returns cosine
    similarity x 100, and cosine similarity is defined on [-1, 1] — a profile
    and a job with nothing in common score *negative*, which is not a number
    the digest has any way to show. The re-ranker's `fit_score` is nominally
    0-1 but comes from an LLM, so it is not guaranteed to stay there either.

    Clamping rather than rejecting: a negative similarity means "actively
    dissimilar", which is exactly what the threshold filter downstream is for.
    Dropping the row here instead would silently shrink the candidate pool.
    """
    return max(0.0, min(100.0, float(value)))


def recently_notified_job_ids(
    db: Session,
    user_id: str,
    window_days: int = DEFAULT_DEDUPE_WINDOW_DAYS,
) -> set[str]:
    """Job ids this user was already told about inside the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    rows = (
        db.query(NotificationLogORM.job_ids)
        .filter(
            NotificationLogORM.user_id == user_id,
            NotificationLogORM.status == "sent",
            NotificationLogORM.created_at >= cutoff,
        )
        .all()
    )

    seen: set[str] = set()
    for (raw,) in rows:
        if not raw:
            continue
        try:
            job_ids = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(job_ids, list):
            seen.update(str(job_id) for job_id in job_ids)
    return seen


def _as_posting(row: JobPostingORM) -> Optional[JobPosting]:
    """Validate one stored row into a `JobPosting`, or None.

    `JobPosting` enforces a non-empty title and an http URL, so a row that
    predates those checks — or was written by hand — raises here. This runs
    inside a loop over up to 200 rows, and letting one bad row raise would cost
    the user their entire digest rather than one line of it.
    """
    try:
        return orm_to_job_posting(row)
    except ValidationError:
        logger.warning(
            "Stored job %s does not satisfy JobPosting; omitting", row.job_id
        )
        return None


def _reason_from(entry: Dict[str, Any]) -> Optional[str]:
    """The one-line fit explanation, if the agent produced one.

    `explanation` is a serialized `MatchExplanation`; the digest renders its
    `overall_alignment_summary` and drops the rest. The strengths / gaps /
    next-steps lists belong in the app, where the user can act on them — an
    email that reproduces all four would be a wall of text, and the point of
    the digest is to get them to open the app.
    """
    explanation = entry.get("explanation")
    if not isinstance(explanation, dict):
        return None
    summary = explanation.get("overall_alignment_summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None


def _pipeline_matches(
    db: Session, recipient: DigestRecipient, top_k: int
) -> List[TopJobMatch]:
    """Run the real pipeline and translate its output into TopJobMatch.

    Postings are joined back from SQLite on `job_id` because the Qdrant payload
    carries identity fields only, and the digest renders location, skills,
    work mode and source. That join is the same one the explanation stage
    already does — see `matching_pipeline.explain_ranked_job`.
    """
    from backend.services.matching_pipeline import run_match_pipeline

    ranked = run_match_pipeline(recipient.profile, top_k=top_k, session=db)

    matches: List[TopJobMatch] = []
    for entry in ranked:
        job_id = entry.get("job_id")
        row = db.get(JobPostingORM, job_id) if job_id else None
        if row is None:
            # Qdrant and SQLite have drifted. Naming a job we cannot look up
            # would mean inventing its details, so it is dropped.
            logger.warning("Ranked job %s is not in SQLite; omitting", job_id)
            continue

        posting = _as_posting(row)
        if posting is None:
            continue

        matches.append(
            TopJobMatch(
                job=posting,
                match_score=_clamp_score(
                    float(entry.get("fit_score") or 0.0) * FIT_SCORE_SCALE
                ),
                reason=_reason_from(entry),
            )
        )
    return matches


def _candidate_rows(db: Session, limit: int) -> Sequence[JobPostingORM]:
    return (
        db.query(JobPostingORM)
        .order_by(JobPostingORM.date.desc())
        .limit(limit)
        .all()
    )


def _fallback_matches(
    db: Session, recipient: DigestRecipient, candidate_limit: int
) -> List[TopJobMatch]:
    """Cosine-similarity scoring over SQLite, for when Qdrant is unavailable.

    The scorer is imported lazily: it builds a SentenceTransformer at module
    import, which downloads ~90MB of weights the first time. Importing it here
    rather than at module top keeps this module — and the dispatcher and
    scheduler that import it — cheap to import and testable without the model.
    """
    from backend.features.matching.scorer import calculate_match_score
    from backend.services.matching_pipeline import build_profile

    profile = build_profile(recipient.profile)
    if not profile.skills:
        # The scorer returns 0.0 for an empty profile, so every job would tie
        # at zero and the "top 3" would be an arbitrary three.
        logger.info(
            "No skills in the stored profile for %s; fallback scoring skipped",
            recipient.user_id,
        )
        return []

    matches: List[TopJobMatch] = []
    for row in _candidate_rows(db, candidate_limit):
        posting = _as_posting(row)
        if posting is None:
            continue
        matches.append(
            TopJobMatch(
                job=posting,
                match_score=_clamp_score(calculate_match_score(profile, posting)),
                # No explanation on this path: the agent runs inside the
                # pipeline, and the whole reason we are here is that the
                # pipeline did not.
                reason=None,
            )
        )
    return matches


@dataclass
class Selection:
    """What selection produced, and enough of why to explain an empty result.

    The counters exist because "nothing to send" has two completely different
    causes with opposite fixes: nothing scored well enough (lower the bar, or
    ingest more), versus plenty scored well enough but the reader has already
    been told about all of it (wait, or stop suppressing). Reporting both as
    "nothing cleared your threshold" sent people to tune a slider that was
    never involved — and no threshold, however low, can surface a job that is
    being excluded by id.

    Counted during the one pass that already happens, rather than by scoring
    twice: the pipeline is four sequential model calls and is not something to
    run again just to write a better sentence.
    """

    matches: List[TopJobMatch]
    #: Scored at or above the recipient's `min_match_score`.
    cleared_threshold: int = 0
    #: Of those, dropped because they were already sent inside the window.
    suppressed_as_recent: int = 0


def select_top_matches(
    db: Session,
    recipient: DigestRecipient,
    top_n: int = DEFAULT_TOP_N,
    exclude_job_ids: Optional[set[str]] = None,
) -> Selection:
    """Return this recipient's best `top_n` jobs, highest score first.

    Applies, in order: score (pipeline, else fallback) -> `min_match_score`
    threshold -> de-duplication -> sort -> top-N truncation.

    An empty stored profile returns an empty list rather than an arbitrary
    three: with nothing to match against, "your top matches" would be a lie.
    """
    exclude_job_ids = exclude_job_ids or set()

    if not recipient.profile:
        logger.info(
            "No stored profile for %s; nothing to match against", recipient.user_id
        )
        return Selection(matches=[])

    try:
        matches = _pipeline_matches(db, recipient, PIPELINE_TOP_K)
    except Exception:
        # Qdrant down, locked by another process, or the LLM gateway
        # unreachable. Logged with a traceback because "the digest was thin
        # today" is otherwise indistinguishable from "the digest is broken".
        logger.exception(
            "Matching pipeline failed for %s; falling back to the scorer",
            recipient.user_id,
        )
        matches = []

    if not matches:
        matches = _fallback_matches(db, recipient, FALLBACK_CANDIDATE_LIMIT)

    # Threshold first, then suppression, so the two can be counted separately.
    # Ordered this way the counters mean what their names say: how many were
    # good enough, and how many of those the reader had already seen.
    good = [
        match for match in matches if match.match_score >= recipient.min_match_score
    ]
    kept = [match for match in good if match.job.job_id not in exclude_job_ids]
    kept.sort(key=lambda match: match.match_score, reverse=True)

    return Selection(
        matches=kept[:top_n],
        cleared_threshold=len(good),
        suppressed_as_recent=len(good) - len(kept),
    )


def get_top_matches(
    db: Session,
    recipient: DigestRecipient,
    top_n: int = DEFAULT_TOP_N,
    exclude_job_ids: Optional[set[str]] = None,
) -> List[TopJobMatch]:
    """Just the matches, for callers that do not need to explain an empty one."""
    return select_top_matches(
        db, recipient, top_n=top_n, exclude_job_ids=exclude_job_ids
    ).matches
