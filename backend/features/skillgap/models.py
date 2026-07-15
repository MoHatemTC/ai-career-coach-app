"""
Skill Gap Database Models

This module contains SQLAlchemy ORM models for persisting skill gap analyses.
These models are designed to integrate with a PostgreSQL database (as recommended
in the project PRD) via SQLAlchemy.

Note: The actual database base and session management are expected to be provided
by the shared core app factory (when it's implemented). These models follow the
standard SQLAlchemy patterns and can be registered with the app's Base class.

Models:
- SkillGapAnalysis: Persists skill gap analysis results for audit and analytics
- SkillGapSkillEntry: Individual skill entries within a gap analysis
"""

from typing import Optional, List
from datetime import datetime
from enum import Enum

# Note: These imports would come from the shared core when it's available
# For now, this is structured to be compatible with future integration
# from backend.core.database import Base
# from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Enum as SQLEnum
# from sqlalchemy.orm import relationship


class SkillGapAnalysisModel:
    """
    Database model for storing skill gap analysis results.
    
    This model persists the results of skill gap analyses for:
    - Historical tracking of user skill development
    - Analytics on common skill gaps by role
    - Audit trail of recommendations given to users
    - Future AI training data for improved role templates
    
    In actual implementation, this would inherit from SQLAlchemy Base:
    
    ```python
    class SkillGapAnalysis(Base):
        __tablename__ = "skill_gap_analyses"
        
        id = Column(String, primary_key=True)
        user_id = Column(String, index=True)
        target_role = Column(String)
        ...
    ```
    """
    
    # These would be actual SQLAlchemy Column definitions
    __tablename__ = "skill_gap_analyses"
    
    # Primary key
    id: str  # UUID - primary key
    
    # Foreign keys and relationships
    user_id: Optional[str]  # Reference to user, if available
    profile_id: Optional[str]  # Reference to persisted profile, if available
    
    # Analysis input
    target_role: str  # The job role being analyzed
    
    # Analysis output
    match_percentage: float  # 0-100 percentage match
    critical_gaps_count: int  # Count of critical priority gaps
    
    # Skill data (serialized as JSON in database)
    profile_skills: List[str]  # Skills the user has
    required_skills: List[dict]  # Required skills with priority and market demand
    skills_match: List[str]  # Skills where user meets requirements
    skill_gaps: List[dict]  # Serialized GapItem objects
    
    # Analysis metadata
    analysis_type: str  # "baseline", "ai_powered", etc.
    analysis_notes: Optional[str]  # Additional notes from analyzer
    
    # Timestamps
    created_at: datetime  # When analysis was created
    updated_at: datetime  # When analysis was last updated
    expires_at: Optional[datetime]  # When analysis is considered stale
    
    @classmethod
    def from_skillgap_schema(cls, skill_gap, user_id: Optional[str] = None):
        """
        Create a database model instance from a SkillGap schema.
        
        Args:
            skill_gap: SkillGap Pydantic model instance
            user_id: User ID (optional, can come from skill_gap)
        
        Returns:
            SkillGapAnalysisModel instance ready for database persistence
        """
        # This would be implemented in actual SQLAlchemy model
        pass
    
    def to_schema(self):
        """
        Convert database model back to SkillGap schema.
        
        Returns:
            SkillGap Pydantic model instance
        """
        # This would be implemented in actual SQLAlchemy model
        pass


class SkillGapSkillEntryModel:
    """
    Database model for individual skill entries within a gap analysis.
    
    This allows for more granular querying and analytics on specific skills.
    For example: "What are the most common missing skills across all analyses?"
    
    In actual implementation:
    
    ```python
    class SkillGapSkillEntry(Base):
        __tablename__ = "skill_gap_skill_entries"
        
        id = Column(String, primary_key=True)
        analysis_id = Column(String, ForeignKey("skill_gap_analyses.id"))
        analysis = relationship("SkillGapAnalysis")
        
        skill_name = Column(String, index=True)
        is_match = Column(Boolean)  # True if skill matches, False if gap
        priority = Column(SQLEnum(...))
        ...
    ```
    """
    
    __tablename__ = "skill_gap_skill_entries"
    
    # Primary key
    id: str  # UUID
    
    # Foreign key
    analysis_id: str  # Reference to SkillGapAnalysis
    
    # Skill information
    skill_name: str  # Canonical skill name
    is_match: bool  # True if user has this skill, False if gap
    
    # Gap-specific fields (only populated if is_match == False)
    gap_reason: Optional[str]
    gap_priority: Optional[str]  # "critical", "high", "medium", "low"
    
    # Match-specific fields (if applicable)
    user_proficiency: Optional[str]  # "beginner", "intermediate", "advanced", "expert"
    
    # Analytics
    market_demand_percentage: Optional[float]  # 0-100 from market data


# ============================================================================
# DATABASE QUERY UTILITIES (for future use)
# ============================================================================

class SkillGapQueryUtilities:
    """
    Utility functions for querying skill gap analyses from the database.
    
    These would be implemented once database setup is available.
    """
    
    @staticmethod
    async def get_user_latest_analysis(user_id: str, target_role: str):
        """
        Get the most recent skill gap analysis for a user and role.
        
        Args:
            user_id: User identifier
            target_role: Target job role
        
        Returns:
            SkillGapAnalysisModel or None if not found
        """
        pass
    
    @staticmethod
    async def get_user_analysis_history(user_id: str, limit: int = 10):
        """
        Get analysis history for a user (most recent first).
        
        Args:
            user_id: User identifier
            limit: Maximum number of results to return
        
        Returns:
            List of SkillGapAnalysisModel instances
        """
        pass
    
    @staticmethod
    async def get_most_common_gaps(target_role: str, limit: int = 10):
        """
        Get the most commonly occurring skill gaps for a target role.
        
        Useful for understanding what skills are most challenging for a role.
        
        Args:
            target_role: Target job role
            limit: Maximum number of results
        
        Returns:
            List of (skill_name, gap_count) tuples
        """
        pass
    
    @staticmethod
    async def get_skill_demand_statistics(skill_name: str):
        """
        Get statistics about demand for a particular skill across all analyses.
        
        Args:
            skill_name: Canonical skill name
        
        Returns:
            Dict with count, percentage, trend data
        """
        pass


# Documentation for future implementation
"""
IMPLEMENTATION NOTES:

1. When database setup is available:
   - Import Base from backend.core.database
   - Make SkillGapAnalysisModel and SkillGapSkillEntryModel inherit from Base
   - Add Column definitions and relationships
   - Register models with the app

2. Indexes to create:
   - analysis_id on skill_gap_analyses (primary)
   - user_id, created_at on skill_gap_analyses (for quick user lookups)
   - analysis_id on skill_gap_skill_entries (foreign key)
   - skill_name on skill_gap_skill_entries (for skill analytics)
   - (analysis_id, skill_name) as composite index

3. Migrations:
   - Use Alembic for schema migrations
   - Create migrations when adding these models to the app

4. Performance considerations:
   - Skill entries should be bulk-inserted with the analysis
   - Periodic cleanup of old/expired analyses (30+ days)
   - Consider materialized views for common analytics queries

5. Data privacy:
   - PII should not be stored in analysis data
   - User IDs should be anonymized for analytics queries
   - Implement data retention policies
"""
