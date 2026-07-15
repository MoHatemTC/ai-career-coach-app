"""Skill-gap analyzer service.

Purpose (PRD Section 7.6):
Compare a user's (normalized) skills against the skills required for a
target role, and produce a prioritized list of gaps.

Sprint 1 scope - "naive baseline" by design:
This is intentionally a frequency-based baseline, NOT an LLM call:
  - required skills for a role = skills that appear across the job
    postings supplied for that role (a simple demand signal), or an
    explicit `required_skills` override if the caller already knows them.
  - priority = how often a missing skill appears across those postings
    (higher frequency -> higher priority -> lower `priority` number).
  - ties are broken alphabetically for determinism (important for
    reproducible tests and explainability).

This keeps Sprint 1 deterministic, cheap, and testable, per PRD Section
11 (cost control) and Section 9 (transparency: every gap must be
explainable, not an opaque score). A later sprint can layer an LLM-based
semantic pass (PRD Section 8 "job matching" / "skill-gap analysis") on
top of this baseline - e.g. to catch synonyms this taxonomy doesn't
know about yet - without changing the `SkillGap` contract.

This module depends only on:
  - `backend.models.profile.Profile` (shared profile contract, stubbed
    for now - see that file's docstring)
  - `backend.models.skill_gap.SkillGap` / `SkillGapItem`
  - `backend.services.skill_taxonomy` (normalization)
It does not import FastAPI, so it is usable from routes, scripts, or
tests without spinning up the web app.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, List, Optional, Sequence

from backend.models.profile import Profile
from backend.models.skill_gap import SkillGap, SkillGapItem
from backend.services.skill_taxonomy import normalize_skills, CATEGORIES


def _derive_required_skills(
    job_postings_skills: Sequence[Iterable[str]],
) -> Counter:
    """Count normalized-skill frequency across a set of job postings.

    Each item in `job_postings_skills` is the raw skill list of one job
    posting. Returns a Counter of canonical skill name -> number of
    postings it appeared in.
    """
    counter: Counter = Counter()
    for raw_skills in job_postings_skills:
        # De-duplicate within a single posting first, so a posting that
        # lists "JS" and "JavaScript" separately doesn't count twice for
        # the same job.
        canonical_in_posting = {ns.canonical for ns in normalize_skills(raw_skills)}
        counter.update(canonical_in_posting)
    return counter


def analyze_skill_gap(
    profile: Profile,
    job_postings_skills: Optional[Sequence[Iterable[str]]] = None,
    required_skills_override: Optional[Iterable[str]] = None,
) -> SkillGap:
    """Compute a naive, frequency-based skill gap for a profile.

    Args:
        profile: The user's profile (must have `target_role` set for a
            meaningful label; skills are read from `profile.skills`).
        job_postings_skills: Raw skill lists, one per job posting, used
            as the demand signal for the target role. Optional so the
            analyzer can also be called with an explicit skill list
            (see `required_skills_override`) when no postings are
            available yet (e.g. early in Sprint 1 before job ingestion
            exists).
        required_skills_override: If provided, used directly as the
            required-skill set instead of deriving it from postings.
            Every overridden skill gets priority based on position in
            the list (earlier = more important), since there is no
            frequency signal to rank by.

    Returns:
        A `SkillGap` with `held_skills`, `matched_skills`, and a
        prioritized `gaps` list.

    Raises:
        ValueError: if neither `job_postings_skills` nor
            `required_skills_override` is supplied - the analyzer has
            nothing to compare against otherwise.
    """
    if not job_postings_skills and not required_skills_override:
        raise ValueError(
            "analyze_skill_gap requires either job_postings_skills or "
            "required_skills_override to determine what skills are needed."
        )

    held = normalize_skills(profile.skills)
    held_canonical = {ns.canonical for ns in held}

    gap_items: List[SkillGapItem] = []
    required_canonical: List[str]

    if required_skills_override is not None:
        override_list = normalize_skills(required_skills_override)
        required_canonical = [ns.canonical for ns in override_list]
        missing_ranked = [
            (skill, position)
            for position, skill in enumerate(required_canonical)
            if skill not in held_canonical
        ]
        # Lower position (appeared earlier) => higher priority (lower number).
        missing_ranked.sort(key=lambda pair: (pair[1], pair[0]))
        for priority, (skill, _position) in enumerate(missing_ranked, start=1):
            gap_items.append(
                SkillGapItem(
                    skill=skill,
                    category=CATEGORIES.get(skill),
                    priority=priority,
                    reason=(
                        f"'{skill}' was explicitly listed as required for "
                        f"'{profile.target_role or 'the target role'}', but "
                        "was not found in the user's profile."
                    ),
                )
            )
    else:
        frequency = _derive_required_skills(job_postings_skills)  # type: ignore[arg-type]
        required_canonical = list(frequency.keys())
        missing = [skill for skill in required_canonical if skill not in held_canonical]
        # Higher frequency => higher priority (lower number). Deterministic
        # tie-break alphabetically.
        missing.sort(key=lambda skill: (-frequency[skill], skill))
        total_postings = len(job_postings_skills)  # type: ignore[arg-type]
        for priority, skill in enumerate(missing, start=1):
            count = frequency[skill]
            gap_items.append(
                SkillGapItem(
                    skill=skill,
                    category=CATEGORIES.get(skill),
                    priority=priority,
                    reason=(
                        f"'{skill}' appeared in {count} of {total_postings} "
                        f"matched job posting(s) for "
                        f"'{profile.target_role or 'the target role'}', but "
                        "was not found in the user's profile."
                    ),
                )
            )

    matched = sorted(s for s in required_canonical if s in held_canonical)

    return SkillGap(
        user_id=profile.user_id,
        target_role=profile.target_role or "",
        required_skills=required_canonical,
        held_skills=[ns.canonical for ns in held],
        matched_skills=matched,
        gaps=gap_items,
    )
