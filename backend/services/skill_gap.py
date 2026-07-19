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

This keeps the baseline deterministic, cheap, and testable, per PRD
Section 11 (cost control) and Section 9 (transparency: every gap must
be explainable, not an opaque score).

Optional semantic pass:
`analyze_skill_gap` can optionally layer an LLM-based semantic pass
(`backend.services.gemini_matcher`, `use_semantic_matching=True`) on
top of this baseline, to catch synonyms/near-equivalents the static
taxonomy doesn't know about yet (e.g. "FastAPI" ~ "REST API
Development"). This is strictly additive:
  - Gemini only ever reclassifies skills this baseline already
    determined were missing - it never sees or touches held/matched
    skills that were already resolved deterministically.
  - Gemini never computes match scores, priorities, or
    recommendations - that stays right here, in Python.
  - Defaults to off (`use_semantic_matching=False`), so existing
    callers and the `SkillGap` contract are unchanged unless a caller
    opts in.

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
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from backend.models.profile import Profile
from backend.models.skill_gap import SkillGap, SkillGapItem
from backend.services.skill_taxonomy import normalize_skills, CATEGORIES
from backend.services.gemini_matcher import (
    SemanticMatcher,
    SemanticMatchResult,
    gemini_semantic_match,
)

# Confidence at/above this counts a semantically-matched skill as fully
# covered (moved out of `gaps` and into `matched_skills`). Below this but
# still reported by Gemini, a skill stays a gap but gets an enriched
# reason - see `_apply_semantic_matching`. Kept as a module constant (not
# a magic number inline) so it's one obvious place to tune, and reviewable
# in PRs per CONTRIBUTING.md.
SEMANTIC_MATCH_CONFIDENCE_THRESHOLD = 0.75


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


def _apply_semantic_matching(
    held_canonical: Set[str],
    missing_skills: List[str],
    semantic_matcher: SemanticMatcher,
) -> Tuple[Set[str], Dict[str, str]]:
    """Ask a semantic matcher to catch equivalences the taxonomy missed.

    This is the ONLY place `analyze_skill_gap` talks to Gemini (or any
    other semantic matcher). It never receives more than the leftover
    `missing_skills` the deterministic baseline couldn't already
    resolve, and it never computes scores or priorities itself - it
    only reclassifies which of those leftovers are actually covered.

    Args:
        held_canonical: Candidate's canonical/normalized skills.
        missing_skills: Canonical required skills not already held,
            per the deterministic (exact + alias) comparison.
        semantic_matcher: Callable returning a validated
            SemanticMatchResult (see gemini_matcher.py). Callers are
            responsible for this already being fully validated - this
            function trusts its shape completely.

    Returns:
        A tuple of:
          - newly_matched: canonical skills to move out of `gaps` and
            into `matched_skills` (confidence at/above
            SEMANTIC_MATCH_CONFIDENCE_THRESHOLD).
          - reason_overrides: canonical skill -> richer explanation,
            for skills that remain gaps but got extra context from the
            semantic pass (partial matches, or missing-skill reasons).

    A failed or empty semantic pass (e.g. Gemini unavailable) simply
    yields (set(), {}), since SemanticMatchResult's fallback value
    (gemini_matcher.empty_result()) is already all-empty lists - no
    special-casing needed here.
    """
    if not missing_skills:
        return set(), {}

    missing_set = set(missing_skills)
    result: SemanticMatchResult = semantic_matcher(sorted(held_canonical), missing_skills)

    newly_matched: Set[str] = set()
    reason_overrides: Dict[str, str] = {}

    for pair in result.matched_skills:
        if pair.required_skill in missing_set and pair.confidence >= SEMANTIC_MATCH_CONFIDENCE_THRESHOLD:
            newly_matched.add(pair.required_skill)

    for pair in result.partially_matched:
        if pair.required_skill not in missing_set or pair.required_skill in newly_matched:
            continue
        if pair.confidence >= SEMANTIC_MATCH_CONFIDENCE_THRESHOLD:
            newly_matched.add(pair.required_skill)
            continue
        detail = f" {pair.reason}" if pair.reason else ""
        reason_overrides[pair.required_skill] = (
            f"Partially covered by '{pair.candidate_skill}', which the candidate already "
            f"has (semantic confidence {pair.confidence:.2f}).{detail}"
        )

    for entry in result.missing_skills:
        if entry.required_skill in missing_set and entry.required_skill not in newly_matched:
            if entry.reason:
                reason_overrides.setdefault(entry.required_skill, entry.reason)

    return newly_matched, reason_overrides


def analyze_skill_gap(
    profile: Profile,
    job_postings_skills: Optional[Sequence[Iterable[str]]] = None,
    required_skills_override: Optional[Iterable[str]] = None,
    use_semantic_matching: bool = False,
    semantic_matcher: Optional[SemanticMatcher] = None,
) -> SkillGap:
    """Compute a skill gap for a profile against required skills.

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
        use_semantic_matching: If True, run the Gemini semantic-match
            pass (backend.services.gemini_matcher) on whatever gaps
            remain after the deterministic taxonomy comparison, to
            catch equivalences the static alias table doesn't know
            about yet (e.g. "FastAPI" ~ "REST API Development").
            Defaults to False, which reproduces the original,
            Gemini-free Sprint 1 behavior exactly - existing callers
            and tests are unaffected unless they opt in.
        semantic_matcher: Override for the semantic matcher (mainly for
            tests / DI). If use_semantic_matching is True and this is
            omitted, defaults to gemini_matcher.gemini_semantic_match,
            which itself degrades to a deterministic no-op result if
            Gemini isn't configured or the call/parse fails - see that
            module's docstring.

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

    if use_semantic_matching and gap_items:
        if semantic_matcher is None:
            # gemini_matcher itself only imports the google-genai SDK
            # lazily, inside gemini_semantic_match - so importing the
            # function here at module load time carries no hard
            # dependency on the SDK/network for callers who never opt
            # into semantic matching.
            semantic_matcher = gemini_semantic_match

        newly_matched, reason_overrides = _apply_semantic_matching(
            held_canonical=held_canonical,
            missing_skills=[item.skill for item in gap_items],
            semantic_matcher=semantic_matcher,
        )

        if newly_matched:
            matched = sorted(set(matched) | newly_matched)

        # Rebuild gap_items: drop newly-matched skills, keep original
        # relative ordering (already priority-sorted above), renumber
        # priorities so they stay contiguous starting at 1, and apply
        # any richer reason text the semantic pass supplied.
        remaining = [item for item in gap_items if item.skill not in newly_matched]
        gap_items = [
            SkillGapItem(
                skill=item.skill,
                category=item.category,
                priority=priority,
                reason=reason_overrides.get(item.skill, item.reason),
            )
            for priority, item in enumerate(remaining, start=1)
        ]

    return SkillGap(
        user_id=profile.user_id,
        target_role=profile.target_role or "",
        required_skills=required_canonical,
        held_skills=[ns.canonical for ns in held],
        matched_skills=matched,
        gaps=gap_items,
    )
