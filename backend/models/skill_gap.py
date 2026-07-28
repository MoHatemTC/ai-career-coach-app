"""SkillGap data model.

Purpose (PRD Section 7.6 - Skill-Gap Analysis):
"Compare the user's skills against target roles and current matched
jobs. Produce a prioritized list of missing / underdeveloped skills."

This module defines the shared, serializable shape of a skill-gap
result: what the route returns to the frontend, and (later) what gets
persisted. Kept as a plain dataclass (not tied to SQLAlchemy/Pydantic)
because this repo does not yet have a shared DB base or Pydantic model
convention (see docs/architecture.md - no ORM/base class exists yet).

Persistence note:
There is currently no shared database layer in this repository (no
`backend/models` DB base class, no chosen ORM). Rather than invent a
private one for this lane only, `to_dict()` / `from_dict()` are
provided so results can be:
  - returned directly as JSON from the FastAPI route, and
  - trivially persisted later (e.g. as a JSON column, a row via
    SQLAlchemy, or a document store) once the team picks a DB
    approach, without changing this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass(frozen=True)
class SkillGapItem:
    """A single missing or underdeveloped skill, with priority.

    Attributes:
        skill: Canonical skill name (see `skill_taxonomy.normalize_skill`).
        category: Coarse category (e.g. "language", "framework"), if known.
        priority: 1 = highest priority (most-demanded / most-required),
            higher numbers = lower priority. Ties are broken by the
            analyzer using demand frequency (see `skill_gap` service).
        reason: Short, human-readable justification, so the gap is
            never an opaque score (Responsible AI - Transparency,
            PRD Section 9).
    """

    skill: str
    category: str | None
    priority: int
    reason: str


@dataclass
class SkillGap:
    """Result of a skill-gap analysis for one user against one target role.

    Attributes:
        user_id: Owner of the analysis.
        target_role: Role the gap was computed against (PRD 7.1).
        required_skills: Canonical skills required for the target role,
            as derived from the job(s) considered.
        held_skills: Canonical skills the user already has.
        gaps: Prioritized list of missing/underdeveloped skills.
        matched_skills: Canonical skills present in both required and
            held (kept for transparency/UI - "here's what already fits").
    """

    user_id: str
    target_role: str
    required_skills: List[str] = field(default_factory=list)
    held_skills: List[str] = field(default_factory=list)
    matched_skills: List[str] = field(default_factory=list)
    gaps: List[SkillGapItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "user_id": self.user_id,
            "target_role": self.target_role,
            "required_skills": self.required_skills,
            "held_skills": self.held_skills,
            "matched_skills": self.matched_skills,
            "gaps": [asdict(g) for g in self.gaps],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SkillGap":
        """Rebuild a SkillGap from a plain dict (e.g. loaded from storage)."""
        gaps = [
            SkillGapItem(
                skill=g["skill"],
                category=g.get("category"),
                priority=g["priority"],
                reason=g.get("reason", ""),
            )
            for g in data.get("gaps", [])
        ]
        return SkillGap(
            user_id=data["user_id"],
            target_role=data["target_role"],
            required_skills=list(data.get("required_skills", [])),
            held_skills=list(data.get("held_skills", [])),
            matched_skills=list(data.get("matched_skills", [])),
            gaps=gaps,
        )
