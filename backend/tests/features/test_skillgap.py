"""
Comprehensive tests for skill-gap analysis components.

Tests cover:
- Skill taxonomy normalization and aliasing
- Skill categorization
- SkillGap schema validation
- Profile schema validation
- Skill-gap analyzer logic
- Edge cases and error handling
"""

import pytest
from datetime import datetime

from backend.features.skillgap.taxonomy import (
    SkillTaxonomy,
    SkillCategory,
    get_taxonomy,
    normalize_skill,
    normalize_skills,
)

from backend.features.skillgap.schema import (
    Profile,
    SkillGap,
    GapItem,
    SkillRequirement,
    SkillEntry,
    GapPriority,
    SkillProficiency,
    ExperienceLevel,
    WorkType,
)

from backend.features.skillgap.analyzer import (
    SkillGapAnalyzer,
    get_analyzer,
    analyze_skill_gap,
)


# ============================================================================
# TAXONOMY TESTS
# ============================================================================

class TestSkillTaxonomyNormalization:
    """Test skill normalization and canonicalization."""

    def test_normalize_lowercase_js_to_javascript(self):
        """Test that 'js' normalizes to 'JavaScript'."""
        assert normalize_skill("js") == "JavaScript"

    def test_normalize_uppercase_js_to_javascript(self):
        """Test that 'JS' normalizes to 'JavaScript'."""
        assert normalize_skill("JS") == "JavaScript"

    def test_normalize_python_variants(self):
        """Test that Python variants all normalize to 'Python'."""
        assert normalize_skill("python") == "Python"
        assert normalize_skill("Python") == "Python"
        assert normalize_skill("PYTHON") == "Python"
        assert normalize_skill("python3") == "Python"
        assert normalize_skill("Python3") == "Python"
        assert normalize_skill("py") == "Python"

    def test_normalize_typescript(self):
        """Test TypeScript normalization."""
        assert normalize_skill("ts") == "TypeScript"
        assert normalize_skill("TS") == "TypeScript"
        assert normalize_skill("typescript") == "TypeScript"

    def test_normalize_react(self):
        """Test React normalization."""
        assert normalize_skill("react") == "React"
        assert normalize_skill("React") == "React"
        assert normalize_skill("reactjs") == "React"
        assert normalize_skill("react.js") == "React"

    def test_normalize_database_skills(self):
        """Test database skill normalization."""
        assert normalize_skill("postgres") == "PostgreSQL"
        assert normalize_skill("postgresql") == "PostgreSQL"
        assert normalize_skill("mongo") == "MongoDB"
        assert normalize_skill("mongodb") == "MongoDB"
        assert normalize_skill("sqlite3") == "SQLite"

    def test_normalize_with_whitespace(self):
        """Test normalization strips whitespace."""
        assert normalize_skill("  javascript  ") == "JavaScript"
        assert normalize_skill("\tpython\n") == "Python"

    def test_normalize_nonexistent_skill_returns_none(self):
        """Test that nonexistent skills return None."""
        assert normalize_skill("nonexistent_skill_xyz") is None
        assert normalize_skill("FakeLanguage2000") is None

    def test_normalize_empty_string_returns_none(self):
        """Test that empty strings return None."""
        assert normalize_skill("") is None
        assert normalize_skill("   ") is None

    def test_normalize_none_returns_none(self):
        """Test that None input returns None."""
        assert normalize_skill(None) is None

    def test_normalize_skills_list(self):
        """Test normalizing a list of skills."""
        skills = ["js", "python3", "react", "invalid_skill", "PostgreSQL"]
        normalized = normalize_skills(skills)
        
        # Should contain the normalized skills
        assert "JavaScript" in normalized
        assert "Python" in normalized
        assert "React" in normalized
        assert "PostgreSQL" in normalized
        
        # Should not contain invalid skill
        assert ("invalid_skill" in normalized) is False
        
        # Should be deduplicated and sorted
        assert len(set(normalized)) == len(normalized)
        assert normalized == sorted(normalized)

    def test_normalize_skills_removes_duplicates(self):
        """Test that normalize_skills removes duplicates."""
        skills = ["js", "javascript", "Python", "python3", "py"]
        normalized = normalize_skills(skills)
        
        assert normalized.count("JavaScript") == 1
        assert normalized.count("Python") == 1


class TestSkillCategorization:
    """Test skill categorization."""

    def test_get_category_programming_languages(self):
        """Test categorizing programming languages."""
        taxonomy = get_taxonomy()
        
        assert taxonomy.get_category("Python") == SkillCategory.PROGRAMMING_LANGUAGE
        assert taxonomy.get_category("javascript") == SkillCategory.PROGRAMMING_LANGUAGE
        assert taxonomy.get_category("Java") == SkillCategory.PROGRAMMING_LANGUAGE

    def test_get_category_frameworks(self):
        """Test categorizing frameworks."""
        taxonomy = get_taxonomy()
        
        assert taxonomy.get_category("React") == SkillCategory.FRAMEWORK
        assert taxonomy.get_category("django") == SkillCategory.FRAMEWORK
        assert taxonomy.get_category("FastAPI") == SkillCategory.FRAMEWORK

    def test_get_category_databases(self):
        """Test categorizing databases."""
        taxonomy = get_taxonomy()
        
        assert taxonomy.get_category("PostgreSQL") == SkillCategory.DATABASE
        assert taxonomy.get_category("mongo") == SkillCategory.DATABASE
        assert taxonomy.get_category("Redis") == SkillCategory.DATABASE

    def test_get_category_devops_tools(self):
        """Test categorizing DevOps tools."""
        taxonomy = get_taxonomy()
        
        assert taxonomy.get_category("Docker") == SkillCategory.DEVOPS_TOOL
        assert taxonomy.get_category("kubernetes") == SkillCategory.DEVOPS_TOOL
        assert taxonomy.get_category("Git") == SkillCategory.DEVOPS_TOOL

    def test_get_category_soft_skills(self):
        """Test categorizing soft skills."""
        taxonomy = get_taxonomy()
        
        assert taxonomy.get_category("Communication") == SkillCategory.SOFT_SKILL
        assert taxonomy.get_category("problem solving") == SkillCategory.SOFT_SKILL
        assert taxonomy.get_category("Leadership") == SkillCategory.SOFT_SKILL

    def test_get_category_nonexistent_returns_none(self):
        """Test that nonexistent skills return None for category."""
        taxonomy = get_taxonomy()
        assert taxonomy.get_category("NonExistent2000") is None

    def test_get_skills_by_category(self):
        """Test retrieving all skills in a category."""
        taxonomy = get_taxonomy()
        
        prog_langs = taxonomy.get_skills_by_category(SkillCategory.PROGRAMMING_LANGUAGE)
        assert "Python" in prog_langs
        assert "JavaScript" in prog_langs
        assert len(prog_langs) > 0
        
        frameworks = taxonomy.get_skills_by_category(SkillCategory.FRAMEWORK)
        assert "React" in frameworks
        assert "Django" in frameworks
        assert len(frameworks) > 0


class TestTaxonomyAPI:
    """Test the SkillTaxonomy class API."""

    def test_is_valid_skill(self):
        """Test is_valid_skill method."""
        taxonomy = get_taxonomy()
        
        assert taxonomy.is_valid_skill("python") is True
        assert taxonomy.is_valid_skill("JavaScript") is True
        assert taxonomy.is_valid_skill("react") is True
        assert taxonomy.is_valid_skill("NonExistent") is False

    def test_add_skill(self):
        """Test adding a new skill to taxonomy."""
        taxonomy = SkillTaxonomy()  # Create a new instance for this test
        
        # Add a new skill
        taxonomy.add_skill(
            "GoLang",
            SkillCategory.PROGRAMMING_LANGUAGE,
            aliases=["golang", "go"]
        )
        
        # Verify it was added
        assert taxonomy.normalize("golang") == "GoLang"
        assert taxonomy.normalize("go") == "GoLang"
        assert taxonomy.get_category("GoLang") == SkillCategory.PROGRAMMING_LANGUAGE

    def test_get_canonical_skills(self):
        """Test retrieving all canonical skills."""
        taxonomy = get_taxonomy()
        canonical = taxonomy.get_canonical_skills()
        
        # Should be a dict mapping skill name to category
        assert isinstance(canonical, dict)
        assert len(canonical) > 0
        
        # Should contain known skills
        assert "Python" in canonical
        assert "JavaScript" in canonical
        assert canonical["Python"] == SkillCategory.PROGRAMMING_LANGUAGE.value


# ============================================================================
# SCHEMA VALIDATION TESTS
# ============================================================================

class TestProfileSchema:
    """Test Profile schema validation."""

    def test_create_minimal_profile(self):
        """Test creating a profile with minimal fields."""
        profile = Profile()
        
        assert profile.user_id is None
        assert profile.full_name is None
        assert profile.skills == []
        assert profile.target_roles == []
        assert isinstance(profile.created_at, datetime)

    def test_create_full_profile(self):
        """Test creating a profile with all fields."""
        skills = [
            SkillEntry(name="Python", proficiency=SkillProficiency.ADVANCED),
            SkillEntry(name="React", proficiency=SkillProficiency.INTERMEDIATE),
        ]
        
        profile = Profile(
            user_id="user_123",
            full_name="Ahmed Ali",
            current_role="Junior Developer",
            experience_level=ExperienceLevel.JUNIOR,
            target_roles=["Senior Frontend Engineer"],
            skills=skills,
            preferred_locations=["Cairo", "Remote"],
            work_type_preferences=[WorkType.REMOTE, WorkType.FULL_TIME],
            salary_expectations="60k-80k EGP",
            career_goals="Become a tech lead in 5 years",
        )
        
        assert profile.user_id == "user_123"
        assert profile.full_name == "Ahmed Ali"
        assert len(profile.skills) == 2
        assert profile.target_roles == ["Senior Frontend Engineer"]

    def test_profile_validates_skill_entries(self):
        """Test that profile validates skill entries."""
        skills = [
            SkillEntry(name="Python", proficiency=SkillProficiency.ADVANCED),
        ]
        
        profile = Profile(skills=skills)
        assert profile.skills[0].name == "Python"


class TestSkillGapSchema:
    """Test SkillGap schema validation."""

    def test_create_minimal_skillgap(self):
        """Test creating a SkillGap with minimal fields."""
        gap = SkillGap(target_role="Senior Developer")
        
        assert gap.target_role == "Senior Developer"
        assert gap.profile_skills == []
        assert gap.skill_gaps == []
        assert gap.match_percentage == 0.0

    def test_create_full_skillgap(self):
        """Test creating a SkillGap with all fields."""
        gaps = [
            GapItem(
                skill_name="TypeScript",
                priority=GapPriority.HIGH,
                gap_reason="Not held by user",
                recommended_proficiency=SkillProficiency.INTERMEDIATE,
            )
        ]
        
        gap = SkillGap(
            id="gap_123",
            user_id="user_123",
            target_role="Senior Frontend Engineer",
            profile_skills=["JavaScript", "React"],
            skill_gaps=gaps,
            match_percentage=50.0,
            critical_gaps_count=0,
        )
        
        assert gap.id == "gap_123"
        assert gap.target_role == "Senior Frontend Engineer"
        assert len(gap.skill_gaps) == 1
        assert gap.match_percentage == 50.0

    def test_skillgap_match_percentage_bounds(self):
        """Test that match percentage is bounded 0-100."""
        gap = SkillGap(target_role="Developer", match_percentage=75.5)
        assert 0 <= gap.match_percentage <= 100

    def test_gap_item_priority_levels(self):
        """Test GapItem with different priority levels."""
        for priority in [GapPriority.CRITICAL, GapPriority.HIGH, GapPriority.MEDIUM, GapPriority.LOW]:
            gap_item = GapItem(
                skill_name="TestSkill",
                priority=priority,
                gap_reason="Test gap",
            )
            assert gap_item.priority == priority


# ============================================================================
# ANALYZER TESTS
# ============================================================================

class TestSkillGapAnalyzer:
    """Test the skill-gap analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Get a fresh analyzer instance for each test."""
        return SkillGapAnalyzer()

    @pytest.fixture
    def sample_profile(self):
        """Create a sample profile for testing."""
        return Profile(
            user_id="test_user",
            full_name="Test User",
            experience_level=ExperienceLevel.JUNIOR,
            skills=[
                SkillEntry(name="JavaScript", proficiency=SkillProficiency.ADVANCED),
                SkillEntry(name="React", proficiency=SkillProficiency.ADVANCED),
                SkillEntry(name="Git", proficiency=SkillProficiency.INTERMEDIATE),
            ],
        )

    def test_analyze_basic_gap(self, analyzer, sample_profile):
        """Test basic skill-gap analysis."""
        result = analyzer.analyze(sample_profile, "Junior Frontend Developer")
        
        assert isinstance(result, SkillGap)
        assert result.target_role == "Junior Frontend Developer"
        assert len(result.required_skills) > 0
        assert len(result.profile_skills) == 3

    def test_analyze_produces_matches(self, analyzer, sample_profile):
        """Test that analyzer identifies matching skills."""
        result = analyzer.analyze(sample_profile, "Junior Frontend Developer")
        
        # Profile has JavaScript and React, both required for frontend role
        assert "JavaScript" in result.skills_match
        assert "React" in result.skills_match

    def test_analyze_produces_gaps(self, analyzer, sample_profile):
        """Test that analyzer identifies skill gaps."""
        result = analyzer.analyze(sample_profile, "Senior Frontend Engineer")
        
        # Senior role requires more skills (e.g., TypeScript)
        # Profile doesn't have TypeScript, so it should be a gap
        gap_names = {gap.skill_name for gap in result.skill_gaps}
        assert len(gap_names) > 0

    def test_match_percentage_calculation(self, analyzer, sample_profile):
        """Test match percentage calculation."""
        result = analyzer.analyze(sample_profile, "Junior Frontend Developer")
        
        # Match percentage should be between 0 and 100
        assert 0 <= result.match_percentage <= 100

    def test_critical_gaps_counting(self, analyzer, sample_profile):
        """Test that critical gaps are counted."""
        result = analyzer.analyze(sample_profile, "Senior Frontend Engineer")
        
        # Count gaps with critical priority
        critical_count = sum(1 for gap in result.skill_gaps if gap.priority == GapPriority.CRITICAL)
        assert critical_count == result.critical_gaps_count

    def test_analyze_empty_profile(self, analyzer):
        """Test analysis on profile with no skills."""
        empty_profile = Profile(user_id="empty_user")
        result = analyzer.analyze(empty_profile, "Junior Developer")
        
        assert result.profile_skills == []
        assert result.match_percentage == 0.0
        assert len(result.skill_gaps) > 0

    def test_analyze_different_role_templates(self, analyzer, sample_profile):
        """Test analysis across different role templates."""
        roles = ["Junior Frontend Developer", "Backend Developer", "Full Stack Developer"]
        
        for role in roles:
            result = analyzer.analyze(sample_profile, role)
            assert result.target_role == role
            assert len(result.required_skills) > 0

    def test_analyze_generic_role_fallback(self, analyzer, sample_profile):
        """Test analysis for role not in templates."""
        result = analyzer.analyze(sample_profile, "Obscure Role XYZ")
        
        # Should still produce a result with generic requirements
        assert result.target_role == "Obscure Role XYZ"
        assert len(result.required_skills) > 0

    def test_gap_priority_ordering(self, analyzer, sample_profile):
        """Test that gaps are sorted by priority."""
        result = analyzer.analyze(sample_profile, "Senior Frontend Engineer")
        
        # Gaps should be sorted by priority
        if len(result.skill_gaps) > 1:
            priorities = [gap.priority.value for gap in result.skill_gaps]
            # Critical should come before High, etc.
            critical_indices = [i for i, p in enumerate(priorities) if p == "critical"]
            high_indices = [i for i, p in enumerate(priorities) if p == "high"]
            if critical_indices and high_indices:
                assert max(critical_indices) <= min(high_indices) or not high_indices


class TestAnalyzerConvenienceFunctions:
    """Test convenience functions."""

    def test_analyze_skill_gap_function(self):
        """Test the convenience analyze_skill_gap function."""
        profile = Profile(
            skills=[
                SkillEntry(name="Python", proficiency=SkillProficiency.ADVANCED),
            ]
        )
        
        result = analyze_skill_gap(profile, "Backend Developer")
        
        assert isinstance(result, SkillGap)
        assert result.target_role == "Backend Developer"

    def test_get_analyzer_singleton(self):
        """Test that get_analyzer returns singleton."""
        analyzer1 = get_analyzer()
        analyzer2 = get_analyzer()
        
        assert analyzer1 is analyzer2


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_normalize_with_special_characters(self):
        """Test normalization handles special characters."""
        # C# should normalize properly despite special char
        assert normalize_skill("c#") == "C#"
        assert normalize_skill("C++") == "C++"

    def test_profile_with_null_dates(self):
        """Test profile handles null dates gracefully."""
        profile = Profile(
            skills=[
                SkillEntry(name="Python", last_used=None),
            ]
        )
        
        assert profile.skills[0].last_used is None

    def test_analyzer_with_special_characters_in_role(self):
        """Test analyzer handles role names with special characters."""
        profile = Profile()
        analyzer = SkillGapAnalyzer()
        
        # Should not crash on unusual role names
        result = analyzer.analyze(profile, "C# .NET Developer")
        assert result.target_role == "C# .NET Developer"

    def test_skillgap_schema_with_extreme_values(self):
        """Test schema validates extreme but valid values."""
        gap = SkillGap(
            target_role="Test Role",
            match_percentage=100.0,
            critical_gaps_count=999,
        )
        
        assert gap.match_percentage == 100.0
        assert gap.critical_gaps_count == 999

    def test_profile_with_duplicate_skills(self):
        """Test profile handles duplicate skills."""
        skills = [
            SkillEntry(name="Python"),
            SkillEntry(name="Python"),  # Duplicate
        ]
        
        # Profile should accept it (UI should deduplicate)
        profile = Profile(skills=skills)
        assert len(profile.skills) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
