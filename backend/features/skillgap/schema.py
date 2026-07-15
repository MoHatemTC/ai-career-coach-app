"""
Skill Gap Analysis Schemas

This module defines the Pydantic data models for skill-gap analysis components.
These schemas form the shared contract between the Profile intake, SkillGap analyzer,
and the frontend.

Key models:
- Profile: User's skills, experience, and career goals
- SkillGap: Comparison of profile skills vs. target role requirements
- SkillRequirement: A single skill with demand level and importance
- GapItem: A prioritized gap in the profile
"""

from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ExperienceLevel(str, Enum):
    """User experience level for targeting roles."""
    ENTRY_LEVEL = "entry_level"
    JUNIOR = "junior"
    MID_LEVEL = "mid_level"
    SENIOR = "senior"
    LEAD = "lead"


class WorkType(str, Enum):
    """Preferred work arrangement types."""
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    REMOTE = "remote"


class SkillProficiency(str, Enum):
    """Proficiency level of a skill."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class GapPriority(str, Enum):
    """Priority level for skill gaps (higher = more important)."""
    CRITICAL = "critical"  # Must have for target role
    HIGH = "high"  # Strongly preferred
    MEDIUM = "medium"  # Beneficial
    LOW = "low"  # Nice to have


class SkillEntry(BaseModel):
    """A single skill entry in a profile."""
    name: str = Field(..., description="Canonical skill name")
    proficiency: SkillProficiency = Field(
        default=SkillProficiency.INTERMEDIATE,
        description="User's proficiency level with this skill"
    )
    years_of_experience: Optional[float] = Field(
        default=None,
        description="Years of experience with this skill (optional)"
    )
    last_used: Optional[datetime] = Field(
        default=None,
        description="When the skill was last used (optional)"
    )


class Profile(BaseModel):
    """
    User profile with skills, experience, and career goals.
    
    This is the shared contract that the CV parser produces and the SkillGap
    analyzer consumes. The SkillGap analyzer should NOT modify this structure.
    """
    user_id: Optional[str] = Field(None, description="User identifier")
    
    # Basic info
    full_name: Optional[str] = Field(None, description="User's full name")
    current_role: Optional[str] = Field(None, description="Current job title")
    experience_level: ExperienceLevel = Field(
        default=ExperienceLevel.ENTRY_LEVEL,
        description="Current experience level"
    )
    
    # Target roles (can have multiple)
    target_roles: List[str] = Field(
        default_factory=list,
        description="Job titles or roles the user is targeting"
    )
    
    # Skills (normalized)
    skills: List[SkillEntry] = Field(
        default_factory=list,
        description="Skills the user has, normalized to canonical names"
    )
    
    # Career preferences
    preferred_locations: List[str] = Field(
        default_factory=list,
        description="Preferred work locations (e.g., 'Cairo', 'Remote', 'Dubai')"
    )
    
    work_type_preferences: List[WorkType] = Field(
        default_factory=list,
        description="Preferred work types (remote, full-time, contract, etc.)"
    )
    
    salary_expectations: Optional[str] = Field(
        None,
        description="Salary expectations (e.g., '60k-80k', 'competitive', 'open')"
    )
    
    # Career goals (free text)
    career_goals: Optional[str] = Field(
        None,
        description="User's career goals and aspirations (free text)"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "full_name": "Ahmed Ali",
                "current_role": "Junior Developer",
                "experience_level": "junior",
                "target_roles": ["Senior Frontend Engineer", "Tech Lead"],
                "skills": [
                    {
                        "name": "JavaScript",
                        "proficiency": "advanced",
                        "years_of_experience": 3.5
                    },
                    {
                        "name": "React",
                        "proficiency": "advanced",
                        "years_of_experience": 2.0
                    },
                    {
                        "name": "Python",
                        "proficiency": "intermediate",
                        "years_of_experience": 1.0
                    }
                ],
                "preferred_locations": ["Cairo", "Remote"],
                "work_type_preferences": ["remote", "full_time"],
                "salary_expectations": "60k-80k EGP"
            }
        }


class SkillRequirement(BaseModel):
    """A skill required for a target role."""
    name: str = Field(..., description="Canonical skill name")
    priority: GapPriority = Field(
        ...,
        description="How important this skill is for the target role"
    )
    market_demand: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Percentage of job postings requiring this skill (0-100)"
    )


class GapItem(BaseModel):
    """
    A single skill gap in the user's profile relative to a target role.
    Prioritized for learning and development.
    """
    skill_name: str = Field(..., description="Canonical skill name")
    priority: GapPriority = Field(
        ...,
        description="Priority level of this gap"
    )
    gap_reason: str = Field(
        ...,
        description="Why this skill is a gap (e.g., 'Not held by user', 'Underdeveloped')"
    )
    current_proficiency: Optional[SkillProficiency] = Field(
        None,
        description="User's current proficiency (if they have some level)"
    )
    recommended_proficiency: SkillProficiency = Field(
        default=SkillProficiency.INTERMEDIATE,
        description="Recommended proficiency level for the target role"
    )
    suggested_resources: Optional[List[str]] = Field(
        None,
        description="Suggested learning resources or certifications"
    )


class SkillGap(BaseModel):
    """
    The primary SkillGap schema: a comparison of the user's profile against
    a target role, producing a prioritized list of skill gaps.
    
    This is the shared contract between the analyzer and the UI/downstream services.
    """
    id: Optional[str] = Field(None, description="Unique identifier for this gap analysis")
    user_id: Optional[str] = Field(None, description="User identifier")
    
    # Reference to profile and target
    profile_id: Optional[str] = Field(None, description="Reference to the source Profile")
    target_role: str = Field(
        ...,
        description="The job title or role being analyzed"
    )
    
    # Skills breakdown
    profile_skills: List[str] = Field(
        default_factory=list,
        description="List of canonical skills the user holds"
    )
    
    required_skills: List[SkillRequirement] = Field(
        default_factory=list,
        description="Skills required for the target role (from market data or job postings)"
    )
    
    # Gap analysis results
    skills_match: List[str] = Field(
        default_factory=list,
        description="Skills where user meets the target role requirements"
    )
    
    skill_gaps: List[GapItem] = Field(
        default_factory=list,
        description="Prioritized list of skill gaps (sorted by priority)"
    )
    
    # Summary metrics
    match_percentage: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Percentage of required skills the user has (0-100)"
    )
    
    critical_gaps_count: int = Field(
        default=0,
        description="Number of critical priority gaps"
    )
    
    # Analysis metadata
    analysis_type: str = Field(
        default="baseline",
        description="Type of analysis (e.g., 'baseline', 'ai_powered')"
    )
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_notes: Optional[str] = Field(
        None,
        description="Additional notes from the analysis (e.g., about market trends)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "gap_456",
                "user_id": "user_123",
                "target_role": "Senior Frontend Engineer",
                "profile_skills": ["JavaScript", "React", "Python", "Git"],
                "required_skills": [
                    {
                        "name": "JavaScript",
                        "priority": "critical",
                        "market_demand": 95
                    },
                    {
                        "name": "React",
                        "priority": "critical",
                        "market_demand": 85
                    },
                    {
                        "name": "TypeScript",
                        "priority": "high",
                        "market_demand": 70
                    },
                    {
                        "name": "GraphQL",
                        "priority": "high",
                        "market_demand": 45
                    }
                ],
                "skills_match": ["JavaScript", "React"],
                "skill_gaps": [
                    {
                        "skill_name": "TypeScript",
                        "priority": "high",
                        "gap_reason": "Not held by user, highly demanded",
                        "current_proficiency": None,
                        "recommended_proficiency": "advanced",
                        "suggested_resources": ["TypeScript Handbook", "egghead.io TypeScript course"]
                    },
                    {
                        "skill_name": "GraphQL",
                        "priority": "high",
                        "gap_reason": "Not held by user, increasingly demanded",
                        "current_proficiency": None,
                        "recommended_proficiency": "intermediate"
                    }
                ],
                "match_percentage": 50.0,
                "critical_gaps_count": 0,
                "analysis_type": "baseline"
            }
        }


class SkillGapRequest(BaseModel):
    """
    Request body for the skill-gap analysis endpoint.
    Takes a Profile and target role, returns a SkillGap analysis.
    """
    profile: Profile = Field(..., description="User profile to analyze")
    target_role: str = Field(..., description="Target job role to analyze against")
    include_market_data: bool = Field(
        default=False,
        description="Whether to include market demand percentages (requires job data source)"
    )


class SkillGapResponse(BaseModel):
    """
    Response body from the skill-gap analysis endpoint.
    """
    success: bool = Field(..., description="Whether the analysis succeeded")
    skill_gap: Optional[SkillGap] = Field(None, description="The resulting SkillGap analysis")
    errors: Optional[List[str]] = Field(None, description="Any errors encountered")
    warnings: Optional[List[str]] = Field(None, description="Non-fatal warnings")
