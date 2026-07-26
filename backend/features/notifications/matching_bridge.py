"""Adapter between the existing matching pipeline and the digest.

Design rule for this file: **do not reimplement scoring.** The score must come
from `features/matching/scorer.calculate_match_score` so the digest can never
disagree with what /matching/rank-jobs shows in the UI. Everything here is
selection, translation, and filtering around that one call.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Sequence

from sqlalchemy.orm import Session

from backend.features.notifications.schema import TopJobMatch
from backend.models.db_models import (
    JobPostingORM,
    NotificationLogORM,
    orm_to_canonical_job,
    orm_to_job_posting,
)
from backend.models.user import UserRead

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 3

# Scoring is a sentence-transformer encode per job, so cost is linear in the
# candidate pool and this runs for every user every night. Capping the pool to
# the most recent postings keeps a nightly run bounded; freshness is what the
# user cares about in a *daily* digest anyway.
#
# FOLLOW-UP (perf): calculate_match_score() re-encodes the profile text on
# every call, so a run is O(users x jobs) encodes instead of O(users + jobs).
# Fixing it means adding a batch entry point to scorer.py, which the matching
# lane owns — raise it with them rather than forking the scoring logic here.
DEFAULT_CANDIDATE_LIMIT = 200

# How far back to look when suppressing repeats (PRD 7.9 (S)).
DEFAULT_DEDUPE_WINDOW_DAYS = 7


def _score_fn():
    """Import the scorer lazily.

    `features/matching/scorer.py` constructs a SentenceTransformer at module
    import, which downloads ~90MB of model weights the first time. Importing
    it here rather than at module top means this module — and the dispatcher
    and scheduler that import it — stay cheap to import and unit-testable
    without the model present.
    """
    from backend.features.matching.scorer import calculate_match_score

    return calculate_match_score


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
    for (job_ids,) in rows:
        if job_ids:
            seen.update(job_ids)
    return seen


def _candidate_rows(db: Session, limit: int) -> Sequence[JobPostingORM]:
    return (
        db.query(JobPostingORM)
        .order_by(JobPostingORM.date.desc().nullslast())
        .limit(limit)
        .all()
    )


def get_top_matches(
    db: Session,
    user: UserRead,
    top_n: int = DEFAULT_TOP_N,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    exclude_job_ids: set[str] | None = None,
    app_base_url: str = "",
) -> List[TopJobMatch]:
    """Return this user's best `top_n` jobs, highest score first.

    Applies, in order: recency cap -> de-duplication -> scoring ->
    `min_match_score` threshold -> top-N truncation.
    """
    exclude_job_ids = exclude_job_ids or set()
    profile = user.to_profile()
    threshold = user.settings.min_match_score
    calculate_match_score = _score_fn()

    scored: List[TopJobMatch] = []
    for row in _candidate_rows(db, candidate_limit):
        if row.job_id in exclude_job_ids:
            continue

        canonical = orm_to_canonical_job(row, fallback_url_base=app_base_url)
        if canonical is None:
            logger.debug("Skipping job %s: cannot satisfy canonical schema", row.job_id)
            continue

        # Scored against the legacy shape because that is what the matching
        # lane's scorer signature takes today. The canonical object above is
        # what actually ships in the digest.
        score = calculate_match_score(profile, orm_to_job_posting(row))
        if score < threshold:
            continue

        scored.append(TopJobMatch(job=canonical, match_score=score))

    scored.sort(key=lambda match: match.match_score, reverse=True)
    return scored[:top_n]
