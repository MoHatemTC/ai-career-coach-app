"""
Skill Gap Analyzer Service

This module implements the core skill-gap analysis logic. It compares a user's
profile (skills, experience level) against a target role to identify:
- Skill matches (what the user already has)
- Skill gaps (what they need to learn)
- Gap prioritization (what to focus on first)

The analyzer produces a naive baseline gap using:
1. Role-based skill templates (hardcoded requirements for known roles)
2. Profile skill normalization and comparison
3. Priority ranking based on role importance and market demand
"""

from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime

from .taxonomy import get_taxonomy, SkillCategory, normalize_skills
from .schema import (
    Profile, SkillGap, GapItem, SkillRequirement, GapPriority,
    SkillProficiency, SkillEntry
)


# Naive role-based skill requirements template
# Maps target roles to their required skills with priority levels
ROLE_SKILL_TEMPLATES: Dict[str, List[Tuple[str, GapPriority, float]]] = {
    "Junior Frontend Developer": [
        ("JavaScript", GapPriority.CRITICAL, 95),
        ("HTML", GapPriority.CRITICAL, 90),
        ("CSS", GapPriority.CRITICAL, 90),
        ("React", GapPriority.HIGH, 70),
        ("Git", GapPriority.HIGH, 80),
        ("Problem Solving", GapPriority.CRITICAL, 85),
    ],
    "Frontend Engineer": [
        ("JavaScript", GapPriority.CRITICAL, 98),
        ("React", GapPriority.CRITICAL, 90),
        ("TypeScript", GapPriority.HIGH, 75),
        ("CSS", GapPriority.CRITICAL, 85),
        ("Git", GapPriority.CRITICAL, 90),
        ("Testing", GapPriority.HIGH, 70),
        ("Problem Solving", GapPriority.CRITICAL, 90),
    ],
    "Senior Frontend Engineer": [
        ("JavaScript", GapPriority.CRITICAL, 99),
        ("React", GapPriority.CRITICAL, 95),
        ("TypeScript", GapPriority.CRITICAL, 85),
        ("System Design", GapPriority.HIGH, 80),
        ("Performance Optimization", GapPriority.HIGH, 75),
        ("Leadership", GapPriority.HIGH, 60),
        ("Communication", GapPriority.CRITICAL, 85),
    ],
    "Backend Developer": [
        ("Python", GapPriority.CRITICAL, 80),
        ("Django", GapPriority.HIGH, 60),
        ("FastAPI", GapPriority.HIGH, 50),
        ("PostgreSQL", GapPriority.CRITICAL, 85),
        ("Git", GapPriority.CRITICAL, 90),
        ("Problem Solving", GapPriority.CRITICAL, 95),
        ("REST APIs", GapPriority.CRITICAL, 90),
    ],
    "Full Stack Developer": [
        ("JavaScript", GapPriority.CRITICAL, 95),
        ("React", GapPriority.CRITICAL, 85),
        ("Python", GapPriority.CRITICAL, 75),
        ("PostgreSQL", GapPriority.CRITICAL, 80),
        ("Git", GapPriority.CRITICAL, 90),
        ("Docker", GapPriority.HIGH, 65),
        ("Problem Solving", GapPriority.CRITICAL, 95),
    ],
    "DevOps Engineer": [
        ("Docker", GapPriority.CRITICAL, 90),
        ("Kubernetes", GapPriority.CRITICAL, 85),
        ("Linux", GapPriority.CRITICAL, 90),
        ("CI/CD", GapPriority.CRITICAL, 85),
        ("AWS", GapPriority.HIGH, 70),
        ("Terraform", GapPriority.HIGH, 60),
        ("Problem Solving", GapPriority.CRITICAL, 90),
    ],
    "Data Scientist": [
        ("Python", GapPriority.CRITICAL, 99),
        ("Pandas", GapPriority.CRITICAL, 85),
        ("Scikit-learn", GapPriority.CRITICAL, 80),
        ("SQL", GapPriority.CRITICAL, 85),
        ("Data Analysis", GapPriority.CRITICAL, 90),
        ("Statistics", GapPriority.HIGH, 80),
        ("Communication", GapPriority.CRITICAL, 75),
    ],
}


class SkillGapAnalyzer:
    """
    Analyzer for identifying skill gaps between a user profile and target role.
    
    The analyzer produces a naive baseline gap analysis using:
    - Role skill templates (predefined skill requirements)
    - Profile skill normalization
    - Priority-based ranking
    
    This can be extended later with AI-powered analysis or market data.
    """

    def __init__(self):
        """Initialize the analyzer with taxonomy and role templates."""
        self.taxonomy = get_taxonomy()
        self.role_templates = ROLE_SKILL_TEMPLATES

    def analyze(self, profile: Profile, target_role: str, analysis_id: Optional[str] = None) -> SkillGap:
        """
        Perform a naive baseline skill-gap analysis.
        
        Args:
            profile: User profile with skills and experience
            target_role: Target job role (e.g., "Senior Frontend Engineer")
            analysis_id: Optional unique ID for this analysis
        
        Returns:
            SkillGap object with match results and prioritized gaps
        """
        # Normalize and extract profile skills
        profile_skills = self._extract_profile_skills(profile)
        
        # Get required skills for the target role
        required_skills = self._get_required_skills(target_role)
        
        # Find skill matches
        skills_match = self._find_matching_skills(profile_skills, required_skills)
        
        # Identify gaps
        gaps = self._identify_gaps(profile_skills, profile, required_skills, skills_match)
        
        # Calculate metrics
        match_percentage = self._calculate_match_percentage(
            len(skills_match),
            len(required_skills)
        )
        
        critical_gaps = sum(1 for gap in gaps if gap.priority == GapPriority.CRITICAL)
        
        # Build the SkillGap response
        skill_gap = SkillGap(
            id=analysis_id,
            user_id=profile.user_id,
            profile_id=None,  # Would be set if profile was persisted
            target_role=target_role,
            profile_skills=sorted(profile_skills),
            required_skills=required_skills,
            skills_match=sorted(skills_match),
            skill_gaps=sorted(gaps, key=lambda g: (g.priority.value, g.skill_name)),
            match_percentage=match_percentage,
            critical_gaps_count=critical_gaps,
            analysis_type="baseline",
            created_at=datetime.utcnow(),
        )
        
        return skill_gap

    def _extract_profile_skills(self, profile: Profile) -> Set[str]:
        """
        Extract and normalize skills from profile.
        
        Args:
            profile: User profile
        
        Returns:
            Set of canonical skill names
        """
        raw_skills = [skill.name for skill in profile.skills]
        normalized = self.taxonomy.normalize_skills(raw_skills)
        return set(normalized)

    def _get_required_skills(self, target_role: str) -> List[SkillRequirement]:
        """
        Get required skills for a target role using the role template.
        
        Falls back to a generic set if role is not in templates.
        
        Args:
            target_role: Target job role
        
        Returns:
            List of SkillRequirement objects
        """
        # Try exact match first
        if target_role in self.role_templates:
            template = self.role_templates[target_role]
        else:
            # Fall back to generic requirements
            template = self._get_generic_role_requirements(target_role)
        
        required = []
        for skill_name, priority, market_demand in template:
            canonical = self.taxonomy.normalize(skill_name)
            if canonical:
                required.append(
                    SkillRequirement(
                        name=canonical,
                        priority=priority,
                        market_demand=market_demand
                    )
                )
        
        return required

    def _get_generic_role_requirements(self, target_role: str) -> List[Tuple[str, GapPriority, float]]:
        """
        Generate generic role requirements based on role keywords.
        
        This is a fallback for roles not in the template.
        
        Args:
            target_role: Target role name
        
        Returns:
            List of (skill, priority, market_demand) tuples
        """
        generic_skills = [
            ("Problem Solving", GapPriority.CRITICAL, 85),
            ("Communication", GapPriority.HIGH, 75),
            ("Team Collaboration", GapPriority.HIGH, 80),
        ]
        
        # Add tech skills if it seems like a tech role
        role_lower = target_role.lower()
        if any(word in role_lower for word in ["engineer", "developer", "programmer", "tech"]):
            generic_skills.extend([
                ("Git", GapPriority.HIGH, 80),
                ("Python", GapPriority.MEDIUM, 60),
            ])
        
        if any(word in role_lower for word in ["frontend", "ui", "ux"]):
            generic_skills.extend([
                ("JavaScript", GapPriority.HIGH, 90),
            ])
        
        if any(word in role_lower for word in ["backend", "api"]):
            generic_skills.extend([
                ("SQL", GapPriority.HIGH, 85),
                ("REST APIs", GapPriority.HIGH, 80),
            ])
        
        return generic_skills

    def _find_matching_skills(
        self,
        profile_skills: Set[str],
        required_skills: List[SkillRequirement]
    ) -> List[str]:
        """
        Find skills where the user meets requirements.
        
        Args:
            profile_skills: Set of skills the user has
            required_skills: List of skills required for the role
        
        Returns:
            List of matching skill names (canonical)
        """
        required_skill_names = {req.name for req in required_skills}
        matches = profile_skills & required_skill_names
        return sorted(list(matches))

    def _identify_gaps(
        self,
        profile_skills: Set[str],
        profile: Profile,
        required_skills: List[SkillRequirement],
        matching_skills: List[str]
    ) -> List[GapItem]:
        """
        Identify skill gaps and prioritize them.
        
        Args:
            profile_skills: Set of skills the user has
            profile: Full profile object (for proficiency info)
            required_skills: List of required skills
            matching_skills: List of skills that match
        
        Returns:
            List of GapItem objects (sorted by priority)
        """
        gaps: List[GapItem] = []
        matching_set = set(matching_skills)
        
        # Build a lookup of profile skills with proficiency
        skill_proficiency_map: Dict[str, SkillProficiency] = {
            skill.name: skill.proficiency
            for skill in profile.skills
        }
        
        for req in required_skills:
            if req.name not in matching_set:
                # This is a gap
                current_proficiency = skill_proficiency_map.get(req.name)
                
                if current_proficiency:
                    gap_reason = f"Underdeveloped (currently {current_proficiency.value})"
                else:
                    gap_reason = "Not held by user"
                
                # Recommend proficiency based on requirement priority
                recommended = self._recommend_proficiency(req.priority)
                
                gap = GapItem(
                    skill_name=req.name,
                    priority=req.priority,
                    gap_reason=gap_reason,
                    current_proficiency=current_proficiency,
                    recommended_proficiency=recommended,
                    suggested_resources=self._suggest_resources(req.name),
                )
                gaps.append(gap)
        
        return gaps

    def _calculate_match_percentage(self, matched_count: int, total_required: int) -> float:
        """
        Calculate the percentage match between profile and target role.
        
        Args:
            matched_count: Number of skills matching
            total_required: Total required skills
        
        Returns:
            Match percentage (0-100)
        """
        if total_required == 0:
            return 100.0
        return round((matched_count / total_required) * 100, 1)

    def _recommend_proficiency(self, priority: GapPriority) -> SkillProficiency:
        """
        Recommend proficiency level based on skill priority.
        
        Args:
            priority: Priority level of the skill
        
        Returns:
            Recommended SkillProficiency
        """
        if priority == GapPriority.CRITICAL:
            return SkillProficiency.ADVANCED
        elif priority == GapPriority.HIGH:
            return SkillProficiency.INTERMEDIATE
        else:
            return SkillProficiency.BEGINNER

    def _suggest_resources(self, skill_name: str) -> Optional[List[str]]:
        """
        Suggest learning resources for a skill.
        
        This is a naive implementation that can be extended with a resource database.
        
        Args:
            skill_name: Canonical skill name
        
        Returns:
            List of suggested resources or None
        """
        # Naive mapping of skills to common resources
        resources_map = {
            "Python": ["Python Official Documentation", "Real Python", "Codecademy Python Course"],
            "JavaScript": ["MDN Web Docs", "JavaScript.info", "freeCodeCamp JavaScript"],
            "React": ["React Official Docs", "Create React App", "Scrimba React Course"],
            "TypeScript": ["TypeScript Handbook", "egghead.io TypeScript", "Udemy TypeScript Course"],
            "SQL": ["W3Schools SQL", "SQLZoo", "LeetCode Database Problems"],
            "Docker": ["Docker Official Docs", "Docker Get Started", "Play with Docker"],
            "Kubernetes": ["Kubernetes Official Docs", "KubeAcademy", "katakoda.com Kubernetes"],
            "Problem Solving": ["LeetCode", "HackerRank", "Codewars"],
            "Communication": ["Toastmasters", "Public Speaking Courses", "Technical Writing Guide"],
        }
        
        return resources_map.get(skill_name)


# Global analyzer instance (singleton)
_analyzer_instance: Optional[SkillGapAnalyzer] = None


def get_analyzer() -> SkillGapAnalyzer:
    """Get the global skill gap analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = SkillGapAnalyzer()
    return _analyzer_instance


def analyze_skill_gap(profile: Profile, target_role: str) -> SkillGap:
    """
    Convenience function to analyze skill gaps.
    
    Args:
        profile: User profile
        target_role: Target job role
    
    Returns:
        SkillGap analysis result
    """
    return get_analyzer().analyze(profile, target_role)
