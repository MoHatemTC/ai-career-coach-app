"""Wire schemas for the daily digest.

`TopJobMatch.job` is the canonical `backend/models/job.py` `JobPosting` — the
same object `orm_to_job_posting` returns and the same one every other lane
consumes. The digest deliberately has no job schema of its own: a message that
named a field differently from the UI would be the third spelling of the same
posting in this repo.

`match_score` is 0-100. The matching pipeline reports fit on 0-1 and
`matching_bridge` scales it once, on the way in, so everything downstream —
templates included — reads one unit.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.job import JobPosting


class TopJobMatch(BaseModel):
    """One ranked job, as delivered to the user."""

    job: JobPosting
    match_score: float = Field(ge=0.0, le=100.0)
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Plain-language fit explanation (PRD 7.5). Populated from the Match "
            "Explanation Agent's `overall_alignment_summary` when the pipeline "
            "produced one; None on the scorer fallback path, which has no "
            "explanation to give."
        ),
    )


class DigestPayload(BaseModel):
    """Everything a provider needs to render and send one user's digest."""

    user_id: str
    full_name: str
    matches: List[TopJobMatch]
    generated_at: datetime

    def top_score(self) -> float:
        return max((match.match_score for match in self.matches), default=0.0)


class DeliveryResult(BaseModel):
    """Outcome of a single send attempt on a single channel."""

    model_config = ConfigDict(frozen=True)

    channel: str
    provider: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def ok(cls, channel: str, provider: str, message_id: Optional[str] = None):
        return cls(
            channel=channel, provider=provider, success=True, message_id=message_id
        )

    @classmethod
    def failed(cls, channel: str, provider: str, error: str):
        return cls(channel=channel, provider=provider, success=False, error=error)


class DispatchSummary(BaseModel):
    """Result of one full run across all users — what the API and logs report."""

    run_started_at: datetime
    run_finished_at: datetime
    users_considered: int = 0
    users_notified: int = 0
    users_skipped_no_contact: int = 0
    users_skipped_already_sent: int = 0
    users_skipped_no_matches: int = 0
    # Distinct from no_matches: nothing was stored to match against, so the
    # fix is a CV rather than a lower threshold.
    users_skipped_no_profile: int = 0
    # Jobs cleared the threshold but had all been sent inside the de-dupe
    # window. Neither a lower threshold nor more postings fixes this one.
    users_skipped_no_new_matches: int = 0
    deliveries: List[DeliveryResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return (self.run_finished_at - self.run_started_at).total_seconds()
