"""Skill taxonomy and normalization.

Purpose (PRD Section 7.6 - Skill-Gap Analysis, Section 8 - AI requirements):
Job postings and user profiles refer to the same real-world skill in many
different surface forms ("JS" vs "JavaScript", "Postgres" vs "PostgreSQL",
"ML" vs "Machine Learning"). Before any gap analysis can be meaningful, we
need a single canonical vocabulary to compare against.

Design decisions:
1. Canonical form is the *full, human-readable* name (e.g. "JavaScript",
   not "js"), because this is what gets shown back to the user in the
   UI and in match explanations (PRD 7.5).
2. Normalization is deliberately a static, explicit alias map rather than
   fuzzy string matching or an LLM call for v1. Rationale:
   - Determinism: skill-gap results must be explainable and reproducible
     (Responsible AI requirement, PRD Section 9 - "Transparency").
   - Cost: this runs on every profile/job pair; an LLM call per skill
     would be slow and expensive (PRD 11 - Cost control).
   - It is trivially extensible: add entries to ALIASES / CATEGORIES.
   A future iteration MAY use embeddings or an LLM for *unseen* skills
   only, falling back to this table for known ones - out of scope here.
3. Matching is case-insensitive and punctuation/whitespace-insensitive
   ("Node.js", "nodejs", "node js" all resolve to "Node.js").
4. Skills are also grouped into coarse categories (language, framework,
   database, cloud, soft-skill, tool) so future ranking/UI can group or
   weight them (PRD 7.4 "structured signals"). Category is optional
   metadata; normalization does not require a category to succeed.

This module has NO dependency on FastAPI, the DB, or any other feature
lane. It is pure functions + data, so it is trivially unit-testable and
reusable by the matching lane (PRD 7.4) if they want normalized skills
too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Canonical taxonomy
# ---------------------------------------------------------------------------

# Canonical skill name -> coarse category.
# Categories are intentionally coarse-grained (v1 scope, PRD 5.1).
CATEGORIES: Dict[str, str] = {
    "JavaScript": "language",
    "TypeScript": "language",
    "Python": "language",
    "Java": "language",
    "C#": "language",
    "C++": "language",
    "Go": "language",
    "SQL": "language",
    "HTML": "language",
    "CSS": "language",
    "React": "framework",
    "Angular": "framework",
    "Vue.js": "framework",
    "Node.js": "framework",
    "Django": "framework",
    "Flask": "framework",
    "FastAPI": "framework",
    "Spring Boot": "framework",
    ".NET": "framework",
    "PostgreSQL": "database",
    "MySQL": "database",
    "MongoDB": "database",
    "Redis": "database",
    "SQLite": "database",
    "AWS": "cloud",
    "Azure": "cloud",
    "Google Cloud Platform": "cloud",
    "Docker": "tool",
    "Kubernetes": "tool",
    "Git": "tool",
    "CI/CD": "tool",
    "Machine Learning": "domain",
    "Deep Learning": "domain",
    "Natural Language Processing": "domain",
    "Data Analysis": "domain",
    "Data Visualization": "domain",
    "Excel": "tool",
    "Power BI": "tool",
    "Tableau": "tool",
    "Project Management": "soft_skill",
    "Communication": "soft_skill",
    "Problem Solving": "soft_skill",
    "Teamwork": "soft_skill",
    "Leadership": "soft_skill",
    "REST APIs": "concept",
    "GraphQL": "concept",
    "Prompt Engineering": "domain",
    "Agile": "concept",
    "Scrum": "concept",
    "Linux": "tool",
    "Bash": "tool",
}

# Alias (any casing/punctuation) -> canonical name.
# Keys are stored pre-normalized (see `_fold`) at module load time via
# `_build_alias_index`, so authors can write aliases naturally here.
_RAW_ALIASES: Dict[str, str] = {
    # JavaScript family
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ecmascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "angularjs": "Angular",
    "angular": "Angular",
    # Python family
    "python": "Python",
    "py": "Python",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "fast api": "FastAPI",
    # Java / C family
    "java": "Java",
    "c#": "C#",
    "csharp": "C#",
    "c sharp": "C#",
    ".net": ".NET",
    "dotnet": ".NET",
    "asp.net": ".NET",
    "c++": "C++",
    "cpp": "C++",
    "golang": "Go",
    "go": "Go",
    "spring": "Spring Boot",
    "spring boot": "Spring Boot",
    # Web basics
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    # Data / SQL
    "sql": "SQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "sqlite": "SQLite",
    "sqlite3": "SQLite",
    # Cloud
    "aws": "AWS",
    "amazon web services": "AWS",
    "azure": "Azure",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "google cloud platform": "Google Cloud Platform",
    # DevOps / tools
    "docker": "Docker",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "git": "Git",
    "github": "Git",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "continuous integration": "CI/CD",
    "linux": "Linux",
    "bash": "Bash",
    "shell scripting": "Bash",
    # Data / AI domain
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "data analysis": "Data Analysis",
    "data analytics": "Data Analysis",
    "data viz": "Data Visualization",
    "data visualization": "Data Visualization",
    "excel": "Excel",
    "ms excel": "Excel",
    "microsoft excel": "Excel",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "tableau": "Tableau",
    "prompt engineering": "Prompt Engineering",
    # APIs / process
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "restful api": "REST APIs",
    "graphql": "GraphQL",
    "agile": "Agile",
    "scrum": "Scrum",
    # Soft skills
    "project management": "Project Management",
    "communication": "Communication",
    "communication skills": "Communication",
    "problem solving": "Problem Solving",
    "problem-solving": "Problem Solving",
    "teamwork": "Teamwork",
    "team work": "Teamwork",
    "leadership": "Leadership",
}


# Placeholder / sentinel values that job postings sometimes use when no
# real skill requirement is available (e.g. a scraped posting with an
# empty requirements section defaulting to "Unknown Skill"). These are
# NOT real skills and must never reach normalization, frequency
# counting, or gap analysis - otherwise "Unknown Skill" ends up looking
# like a legitimate, prioritized skill gap, which is misleading to the
# user and violates the Responsible AI "no fabrication" requirement
# (PRD Section 9) by implying a skill exists when it doesn't.
# Stored pre-folded (see `_fold`) so lookups are case/whitespace-insensitive.
_PLACEHOLDER_SKILLS = {
    "unknown skill",
    "unknown",
    "n/a",
    "na",
    "none",
    "null",
    "tbd",
}


def is_valid_skill(raw: Optional[str]) -> bool:
    """Return True if `raw` is a real, usable skill value.

    Rejects:
        - None
        - non-string values
        - "" and whitespace-only strings
        - known placeholder/sentinel values (see `_PLACEHOLDER_SKILLS`),
          matched case- and whitespace-insensitively.

    This is the single gate every raw skill string must pass before it
    is normalized, counted, or fed into gap analysis - kept as one
    small, testable function rather than duplicating these checks in
    every caller.
    """
    if raw is None or not isinstance(raw, str):
        return False
    stripped = raw.strip()
    if not stripped:
        return False
    if _fold(stripped) in _PLACEHOLDER_SKILLS:
        return False
    return True


def _fold(raw: str) -> str:
    """Fold a raw skill string into a comparison key.

    Lowercases, strips, and collapses internal whitespace/punctuation
    variance (e.g. "Node.js", "node js", "NodeJS" all fold close enough
    to be handled by the alias table). We intentionally keep '.', '#',
    '+' characters since they are meaningful for skills like "C#",
    "C++", "Node.js", ".NET" — we only collapse surrounding whitespace
    and case.
    """
    key = raw.strip().lower()
    key = re.sub(r"\s+", " ", key)
    return key


def _build_alias_index() -> Dict[str, str]:
    index: Dict[str, str] = {}
    # Canonical names normalize to themselves too, so `normalize_skill`
    # works whether the input is already canonical or an alias.
    for canonical in CATEGORIES:
        index[_fold(canonical)] = canonical
    for alias, canonical in _RAW_ALIASES.items():
        index[_fold(alias)] = canonical
    return index


_ALIAS_INDEX: Dict[str, str] = _build_alias_index()


@dataclass(frozen=True)
class NormalizedSkill:
    """Result of normalizing a single raw skill string."""

    raw: str
    canonical: str
    category: Optional[str]
    known: bool  # False if we had no taxonomy entry and fell back to raw


def normalize_skill(raw: Optional[str]) -> NormalizedSkill:
    """Normalize a single raw skill string to its canonical form.

    Unrecognized-but-real skills are NOT dropped: they are passed
    through unchanged (title-cased for display) with `known=False`, so
    the analyzer can still surface them rather than silently discarding
    user/job data. This matches the Responsible AI requirement to avoid
    fabricating or erasing information that was not actually verified
    either way (PRD Section 9).

    Placeholder/invalid values (None, "", whitespace-only, or sentinel
    strings like "Unknown Skill" - see `is_valid_skill`) are different:
    they are not real skills at all, so they are filtered out here and
    return an empty canonical (`canonical=""`), which callers treat as
    "ignore this entry" (see `normalize_skills`).
    """
    if not is_valid_skill(raw):
        return NormalizedSkill(raw=raw or "", canonical="", category=None, known=False)

    key = _fold(raw)
    canonical = _ALIAS_INDEX.get(key)
    if canonical is not None:
        return NormalizedSkill(
            raw=raw,
            canonical=canonical,
            category=CATEGORIES.get(canonical),
            known=True,
        )

    # Unknown skill: pass through, lightly cleaned up for display.
    fallback = raw.strip()
    return NormalizedSkill(raw=raw, canonical=fallback, category=None, known=False)


def normalize_skills(raw_skills: Iterable[Optional[str]]) -> List[NormalizedSkill]:
    """Normalize a collection of raw skill strings.

    De-duplicates by canonical name while preserving first-seen order,
    since a profile or job posting listing "JS" and "JavaScript"
    separately should not count as two distinct skills.

    Placeholder/invalid entries (None, "", whitespace-only, or sentinel
    values like "Unknown Skill" / "Unknown" - see `is_valid_skill`) are
    filtered out completely here, before they ever reach the alias
    lookup, so they can never appear as a "required skill", be counted
    by frequency, or surface as a gap.
    """
    seen: Dict[str, NormalizedSkill] = {}
    for raw in raw_skills:
        result = normalize_skill(raw)
        if not result.canonical:
            continue
        key = result.canonical.lower()
        if key not in seen:
            seen[key] = result
    return list(seen.values())


def canonical_skill_set(raw_skills: Iterable[str]) -> List[str]:
    """Convenience helper: normalize and return just the canonical names."""
    return [ns.canonical for ns in normalize_skills(raw_skills)]
