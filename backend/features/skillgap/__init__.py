"""
Skill Gap Analysis Feature

This package provides skill taxonomy, gap analysis, and related schemas
for the Sprints Career Coach application.

Main components:
- taxonomy: Skill normalization and categorization
- schema: Pydantic models for Profile, SkillGap, and related data
- analyzer: Core skill-gap analysis logic
"""

from .taxonomy import (
    SkillTaxonomy,
    SkillCategory,
    get_taxonomy,
    normalize_skill,
    normalize_skills,
)

from .schema import (
    Profile,
    SkillGap,
    GapItem,
    SkillRequirement,
    SkillEntry,
    GapPriority,
    SkillProficiency,
    ExperienceLevel,
    WorkType,
    SkillGapRequest,
    SkillGapResponse,
)

from .analyzer import (
    SkillGapAnalyzer,
    get_analyzer,
    analyze_skill_gap,
)

__all__ = [
    # Taxonomy
    "SkillTaxonomy",
    "SkillCategory",
    "get_taxonomy",
    "normalize_skill",
    "normalize_skills",
    # Schema
    "Profile",
    "SkillGap",
    "GapItem",
    "SkillRequirement",
    "SkillEntry",
    "GapPriority",
    "SkillProficiency",
    "ExperienceLevel",
    "WorkType",
    "SkillGapRequest",
    "SkillGapResponse",
    # Analyzer
    "SkillGapAnalyzer",
    "get_analyzer",
    "analyze_skill_gap",
]
