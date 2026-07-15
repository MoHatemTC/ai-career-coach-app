"""
Skill Taxonomy and Normalization Module

This module defines a comprehensive skill taxonomy with canonicalization rules.
It handles skill normalization (e.g., 'JS' → 'JavaScript', 'Python3' → 'Python') 
and skill categorization to support skill-gap analysis across profiles and job postings.

Key responsibilities:
- Maintain a canonical skill taxonomy
- Normalize input skills to their canonical forms
- Categorize skills into types (programming languages, frameworks, databases, soft skills, etc.)
- Detect skill equivalence and aliases
- Support fuzzy matching for misspellings and variations
"""

from typing import Dict, List, Set, Optional, Tuple
from enum import Enum
import re


class SkillCategory(str, Enum):
    """Enum for skill categories used in classification."""
    PROGRAMMING_LANGUAGE = "programming_language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    DEVOPS_TOOL = "devops_tool"
    CLOUD_PLATFORM = "cloud_platform"
    SOFT_SKILL = "soft_skill"
    DOMAIN_SKILL = "domain_skill"
    TOOL = "tool"


class SkillTaxonomy:
    """
    Comprehensive skill taxonomy with normalization, aliasing, and categorization.
    
    This class maintains:
    - Canonical skill names (the "authoritative" form)
    - Aliases mapping (variations → canonical name)
    - Skill categories (for classification and grouping)
    - Case-insensitive lookup and fuzzy matching support
    """

    def __init__(self):
        """Initialize the skill taxonomy with predefined canonical skills and aliases."""
        # Canonical skill registry: skill_name -> category
        self.canonical_skills: Dict[str, SkillCategory] = {
            # Programming Languages
            "Python": SkillCategory.PROGRAMMING_LANGUAGE,
            "JavaScript": SkillCategory.PROGRAMMING_LANGUAGE,
            "TypeScript": SkillCategory.PROGRAMMING_LANGUAGE,
            "Java": SkillCategory.PROGRAMMING_LANGUAGE,
            "C++": SkillCategory.PROGRAMMING_LANGUAGE,
            "C#": SkillCategory.PROGRAMMING_LANGUAGE,
            "Go": SkillCategory.PROGRAMMING_LANGUAGE,
            "Rust": SkillCategory.PROGRAMMING_LANGUAGE,
            "Ruby": SkillCategory.PROGRAMMING_LANGUAGE,
            "PHP": SkillCategory.PROGRAMMING_LANGUAGE,
            "Kotlin": SkillCategory.PROGRAMMING_LANGUAGE,
            "Swift": SkillCategory.PROGRAMMING_LANGUAGE,
            "R": SkillCategory.PROGRAMMING_LANGUAGE,
            "MATLAB": SkillCategory.PROGRAMMING_LANGUAGE,
            "SQL": SkillCategory.PROGRAMMING_LANGUAGE,
            
            # Web Frameworks & Libraries
            "React": SkillCategory.FRAMEWORK,
            "Vue": SkillCategory.FRAMEWORK,
            "Angular": SkillCategory.FRAMEWORK,
            "Django": SkillCategory.FRAMEWORK,
            "Flask": SkillCategory.FRAMEWORK,
            "FastAPI": SkillCategory.FRAMEWORK,
            "Express": SkillCategory.FRAMEWORK,
            "Spring": SkillCategory.FRAMEWORK,
            "Node.js": SkillCategory.FRAMEWORK,
            "Next.js": SkillCategory.FRAMEWORK,
            "Svelte": SkillCategory.FRAMEWORK,
            "Laravel": SkillCategory.FRAMEWORK,
            "ASP.NET": SkillCategory.FRAMEWORK,
            
            # Databases
            "PostgreSQL": SkillCategory.DATABASE,
            "MySQL": SkillCategory.DATABASE,
            "MongoDB": SkillCategory.DATABASE,
            "Redis": SkillCategory.DATABASE,
            "Elasticsearch": SkillCategory.DATABASE,
            "Firebase": SkillCategory.DATABASE,
            "DynamoDB": SkillCategory.DATABASE,
            "SQLite": SkillCategory.DATABASE,
            "Oracle": SkillCategory.DATABASE,
            "Cassandra": SkillCategory.DATABASE,
            "Neo4j": SkillCategory.DATABASE,
            
            # DevOps & Infrastructure
            "Docker": SkillCategory.DEVOPS_TOOL,
            "Kubernetes": SkillCategory.DEVOPS_TOOL,
            "Git": SkillCategory.DEVOPS_TOOL,
            "GitHub": SkillCategory.DEVOPS_TOOL,
            "GitLab": SkillCategory.DEVOPS_TOOL,
            "Jenkins": SkillCategory.DEVOPS_TOOL,
            "Terraform": SkillCategory.DEVOPS_TOOL,
            "Ansible": SkillCategory.DEVOPS_TOOL,
            "Linux": SkillCategory.DEVOPS_TOOL,
            "CI/CD": SkillCategory.DEVOPS_TOOL,
            
            # Cloud Platforms
            "AWS": SkillCategory.CLOUD_PLATFORM,
            "Azure": SkillCategory.CLOUD_PLATFORM,
            "Google Cloud": SkillCategory.CLOUD_PLATFORM,
            "GCP": SkillCategory.CLOUD_PLATFORM,
            "Heroku": SkillCategory.CLOUD_PLATFORM,
            
            # Tools & Libraries
            "Postman": SkillCategory.TOOL,
            "Jira": SkillCategory.TOOL,
            "Figma": SkillCategory.TOOL,
            "Tableau": SkillCategory.TOOL,
            "Power BI": SkillCategory.TOOL,
            "Excel": SkillCategory.TOOL,
            "Pandas": SkillCategory.TOOL,
            "NumPy": SkillCategory.TOOL,
            "Scikit-learn": SkillCategory.TOOL,
            "TensorFlow": SkillCategory.TOOL,
            "PyTorch": SkillCategory.TOOL,
            
            # Soft Skills
            "Communication": SkillCategory.SOFT_SKILL,
            "Problem Solving": SkillCategory.SOFT_SKILL,
            "Team Collaboration": SkillCategory.SOFT_SKILL,
            "Leadership": SkillCategory.SOFT_SKILL,
            "Project Management": SkillCategory.SOFT_SKILL,
            "Time Management": SkillCategory.SOFT_SKILL,
            "Presentation": SkillCategory.SOFT_SKILL,
            "Attention to Detail": SkillCategory.SOFT_SKILL,
        }

        # Aliases mapping: variation → canonical skill
        # Supports common abbreviations, spacing, case variations, etc.
        self.aliases: Dict[str, str] = {
            # JavaScript aliases
            "js": "JavaScript",
            "javascript": "JavaScript",
            "node": "Node.js",
            "nodejs": "Node.js",
            "node.js": "Node.js",
            
            # Python aliases
            "python": "Python",
            "python3": "Python",
            "python2": "Python",
            "py": "Python",
            
            # TypeScript aliases
            "ts": "TypeScript",
            "typescript": "TypeScript",
            
            # React aliases
            "react.js": "React",
            "reactjs": "React",
            
            # Vue aliases
            "vuejs": "Vue",
            "vue.js": "Vue",
            
            # Angular aliases
            "angularjs": "Angular",
            "angular.js": "Angular",
            
            # Database aliases
            "postgres": "PostgreSQL",
            "postgresql": "PostgreSQL",
            "psql": "PostgreSQL",
            "mysql": "MySQL",
            "mongo": "MongoDB",
            "mongodb": "MongoDB",
            "redis": "Redis",
            "elastic": "Elasticsearch",
            "elasticsearch": "Elasticsearch",
            "sql": "SQL",
            "sqlite": "SQLite",
            "sqlite3": "SQLite",
            
            # Docker/K8s aliases
            "k8s": "Kubernetes",
            "k8": "Kubernetes",
            "kubernetes": "Kubernetes",
            
            # Cloud aliases
            "aws": "AWS",
            "amazon web services": "AWS",
            "azure": "Azure",
            "google cloud": "Google Cloud",
            "gcp": "GCP",
            "google cloud platform": "Google Cloud",
            
            # DevOps aliases
            "cicd": "CI/CD",
            "ci/cd": "CI/CD",
            
            # Framework aliases
            "django": "Django",
            "flask": "Flask",
            "fastapi": "FastAPI",
            "express": "Express",
            "expressjs": "Express",
            "express.js": "Express",
            "spring boot": "Spring",
            "springboot": "Spring",
            
            # Soft skills aliases
            "communication": "Communication",
            "teamwork": "Team Collaboration",
            "team work": "Team Collaboration",
            "team collaboration": "Team Collaboration",
            "collaboration": "Team Collaboration",
            "problem solving": "Problem Solving",
            "problem-solving": "Problem Solving",
            "critical thinking": "Problem Solving",
            "leadership": "Leadership",
            "project management": "Project Management",
            "time management": "Time Management",
            "presentation": "Presentation",
            "presentations": "Presentation",
            "public speaking": "Presentation",
        }

        # Build reverse lookup (lowercase canonical → canonical)
        self._lowercase_canonical: Dict[str, str] = {
            skill.lower(): skill for skill in self.canonical_skills.keys()
        }

    def normalize(self, skill: str) -> Optional[str]:
        """
        Normalize a skill string to its canonical form.
        
        Handles:
        - Alias lookup (exact match after stripping/lowercasing)
        - Direct canonical lookup
        - Case-insensitive matching
        
        Args:
            skill: Raw skill string (e.g., 'JS', 'javascript', 'Python3')
        
        Returns:
            Canonical skill name if found, None otherwise
            
        Examples:
            >>> taxonomy.normalize('js')
            'JavaScript'
            >>> taxonomy.normalize('Python3')
            'Python'
            >>> taxonomy.normalize('javascript')
            'JavaScript'
        """
        if not skill or not isinstance(skill, str):
            return None
        
        # Strip whitespace and convert to lowercase for lookup
        cleaned = skill.strip().lower()
        
        if not cleaned:
            return None
        
        # First check aliases
        if cleaned in self.aliases:
            return self.aliases[cleaned]
        
        # Check if directly in canonical (case-insensitive)
        if cleaned in self._lowercase_canonical:
            return self._lowercase_canonical[cleaned]
        
        # No match found
        return None

    def is_valid_skill(self, skill: str) -> bool:
        """
        Check if a skill can be normalized to a canonical form.
        
        Args:
            skill: Skill string to validate
        
        Returns:
            True if skill normalizes to a known canonical skill, False otherwise
        """
        return self.normalize(skill) is not None

    def get_category(self, skill: str) -> Optional[SkillCategory]:
        """
        Get the category of a skill (after normalization).
        
        Args:
            skill: Skill string (e.g., 'Python', 'python', 'py')
        
        Returns:
            SkillCategory enum value if found, None otherwise
            
        Examples:
            >>> taxonomy.get_category('python')
            <SkillCategory.PROGRAMMING_LANGUAGE: 'programming_language'>
            >>> taxonomy.get_category('Django')
            <SkillCategory.FRAMEWORK: 'framework'>
        """
        canonical = self.normalize(skill)
        if canonical is None:
            return None
        return self.canonical_skills.get(canonical)

    def normalize_skills(self, skills: List[str]) -> List[str]:
        """
        Normalize a list of skills, filtering out invalid ones.
        
        Args:
            skills: List of raw skill strings
        
        Returns:
            List of canonical skill names (duplicates removed, sorted)
            
        Examples:
            >>> taxonomy.normalize_skills(['js', 'Python', 'react', 'invalid_skill'])
            ['JavaScript', 'Python', 'React']
        """
        normalized = set()
        for skill in skills:
            canonical = self.normalize(skill)
            if canonical is not None:
                normalized.add(canonical)
        return sorted(list(normalized))

    def get_skills_by_category(self, category: SkillCategory) -> List[str]:
        """
        Get all canonical skills in a given category.
        
        Args:
            category: SkillCategory to filter by
        
        Returns:
            List of canonical skill names in that category (sorted)
        """
        return sorted([
            skill for skill, cat in self.canonical_skills.items()
            if cat == category
        ])

    def add_skill(self, canonical_name: str, category: SkillCategory, aliases: List[str] = None) -> None:
        """
        Add a new skill to the taxonomy.
        
        Args:
            canonical_name: The canonical form of the skill
            category: The category this skill belongs to
            aliases: Optional list of aliases to register
        """
        if not canonical_name or not isinstance(canonical_name, str):
            raise ValueError("canonical_name must be a non-empty string")
        
        self.canonical_skills[canonical_name] = category
        self._lowercase_canonical[canonical_name.lower()] = canonical_name
        
        if aliases:
            for alias in aliases:
                if alias and isinstance(alias, str):
                    self.aliases[alias.strip().lower()] = canonical_name

    def get_canonical_skills(self) -> Dict[str, str]:
        """
        Get all canonical skills with their categories.
        
        Returns:
            Dictionary mapping canonical skill name → category name
        """
        return {
            skill: category.value
            for skill, category in self.canonical_skills.items()
        }


# Global taxonomy instance (singleton pattern)
_taxonomy_instance: Optional[SkillTaxonomy] = None


def get_taxonomy() -> SkillTaxonomy:
    """
    Get the global skill taxonomy instance (lazy initialization).
    
    Returns:
        The singleton SkillTaxonomy instance
    """
    global _taxonomy_instance
    if _taxonomy_instance is None:
        _taxonomy_instance = SkillTaxonomy()
    return _taxonomy_instance


def normalize_skill(skill: str) -> Optional[str]:
    """
    Convenience function to normalize a single skill using the global taxonomy.
    
    Args:
        skill: Raw skill string
    
    Returns:
        Canonical skill name or None
    """
    return get_taxonomy().normalize(skill)


def normalize_skills(skills: List[str]) -> List[str]:
    """
    Convenience function to normalize a list of skills using the global taxonomy.
    
    Args:
        skills: List of raw skill strings
    
    Returns:
        List of canonical skill names (deduplicated, sorted)
    """
    return get_taxonomy().normalize_skills(skills)
