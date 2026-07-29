"""Profile data model.

NOTE (Skill-Gap lane, Sprint 1):
This repository did not yet contain a shared `Profile` model when this
lane started. The CV/Profile intake lane (Section 6.1 / 7.1 of the PRD)
owns this model long-term. This is a MINIMAL, EXPLICIT STUB so the
Skill-Gap feature has a concrete contract to depend on instead of
duplicating its own private notion of "profile".

If/when the CV/Profile lane lands its own `Profile` model:
- Reconcile field names with this stub (skills / target_role /
  experience_level are the fields skill-gap actually reads).
- Delete this stub and re-point the imports in
  `backend/services/skill_gap.py` and `backend/routes/skill_gap.py`.

Keep this file intentionally small. Do not add unrelated fields here;
that duplicates ownership across lanes.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Profile:
    """Minimal profile contract consumed by the skill-gap analyzer.

    Attributes:
        user_id: Identifier of the profile owner.
        skills: Raw skill strings as captured from CV/profile intake
            (un-normalized; the skill-gap lane normalizes them via
            `backend.services.skill_taxonomy`).
        target_role: The role the user is targeting (e.g. "Data Analyst").
            Matches PRD 7.1 "Capture target roles...".
        experience_level: Free-text experience level (e.g. "fresh graduate",
            "junior"), matches PRD persona definitions (Section 4).
    """

    user_id: str
    skills: List[str] = field(default_factory=list)
    target_role: Optional[str] = None
    experience_level: Optional[str] = None
