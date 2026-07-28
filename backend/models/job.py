"""Job data model.

NOTE (Match Explanation Agent lane):
This repository does not yet contain a shared `Job` model (the Job
Parser / Job Database lane owns that long-term - see
`backend/routes/README.md`). This is a MINIMAL, EXPLICIT STUB, in the
same spirit as `backend/models/profile.py`'s stub, so the Match
Explanation Agent has a concrete contract to depend on instead of
duplicating its own private notion of "job".

If/when the Job Parser lane lands its own `Job` model:
- Reconcile field names with this stub (job_id / title / company /
  required_skills are the fields the explanation agent actually
  reads).
- Delete this stub and re-point the import in
  `backend/services/match_explanation_agent.py`.

Keep this file intentionally small. Do not add unrelated fields here;
that duplicates ownership across lanes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class JobInfo:
    """Minimal job contract consumed by the Match Explanation Agent.

    Attributes:
        job_id: Identifier of the job posting.
        title: Job title (e.g. "Backend Developer").
        company: Employer name, if known.
        required_skills: Canonical skills required for the role, as
            already determined upstream (Job Parser + Skill Gap
            Analyzer) - the explanation agent never derives these
            itself.
    """

    job_id: str
    title: str
    company: Optional[str] = None
    required_skills: List[str] = field(default_factory=list)
