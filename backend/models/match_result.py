"""MatchResult data model.

Purpose:
The Match Explanation Agent (`backend/services/match_explanation_agent.py`)
consumes an ALREADY-COMPUTED match result - it must never recalculate
a match score or re-run skill-gap analysis. This model is the explicit,
serializable shape of that existing result: whatever upstream matching
engine produced `match_score` / `matched_skills` / `missing_skills`
(today, effectively derived from `backend.services.skill_gap.SkillGap`
plus a score from wherever the matching engine lives) hands it to this
model unchanged.

This module owns no computation - only the data shape - matching the
pattern used by `backend/models/skill_gap.py` and
`backend/models/profile.py` (plain dataclass + to_dict/from_dict, no
ORM/Pydantic dependency, since this repo has no shared DB layer yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass
class MatchResult:
    """An already-computed candidate-to-job match result.

    Attributes:
        match_score: Overall match score, already computed upstream
            (e.g. 0-100). The explanation agent treats this as fixed
            ground truth - it explains this number, never changes it.
        matched_skills: Canonical skills the candidate already has that
            satisfy a requirement (from the skill-gap analyzer).
        missing_skills: Canonical required skills the candidate does
            not have (from the skill-gap analyzer's `gaps`).
    """

    match_score: float
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "MatchResult":
        """Rebuild a MatchResult from a plain dict (e.g. loaded from storage)."""
        return MatchResult(
            match_score=data["match_score"],
            matched_skills=list(data.get("matched_skills", [])),
            missing_skills=list(data.get("missing_skills", [])),
        )
