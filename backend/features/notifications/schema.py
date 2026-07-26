"""Wire schemas for the daily digest.

=============================================================================
 ACTION REQUIRED — CONFIRM WITH MOHAMED FARAG BEFORE THE DEMO
=============================================================================
The task brief says to "confirm the final output schema" of the matching
pipeline. Here is what this lane assumes, and why:

  * `TopJobMatch.job` is the CANONICAL `backend/models/job.py` JobPosting.
    That file's own docstring calls itself "THE shared job schema for the
    whole project" and warns that duplicate schemas "have already caused
    field-name drift between lanes once". The open branch
    `refactor/align-job-schema` appears to be converging on it.

  * The matching lane currently imports the OTHER model,
    `backend/models/job_posting.py` (`required_skills` / `min_experience` /
    `work_type` / `salary: int`). `matching_bridge.py` translates between
    them so neither lane had to change to ship this feature.

  * `match_score` is 0-100, matching what `features/matching/scorer.py`
    already returns (cosine similarity x 100, rounded to 2dp).

  * `reason` is Optional and currently always None. `MatchResponse` in
    features/matching/schema.py declares an `explanation` field that nothing
    populates yet; the `feat/match-explanation-agent` branch looks like it
    will. When it lands, populate `reason` from it — the digest templates
    already render it when present.

If Mohamed confirms a different final shape, `matching_bridge.py` is the only
file that needs to change. Everything downstream reads `TopJobMatch`.
=============================================================================
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
        description="Plain-language fit explanation. See PRD 7.5. Not yet populated.",
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
    deliveries: List[DeliveryResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return (self.run_finished_at - self.run_started_at).total_seconds()
