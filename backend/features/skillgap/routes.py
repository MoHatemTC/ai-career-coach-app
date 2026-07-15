"""
Skill Gap Analysis API Routes

This module defines the HTTP endpoints for skill-gap analysis.
Routes include:
- POST /skillgap - Analyze skill gaps for a given profile and target role
- GET /skillgap/roles - List available target roles with templates
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, status
import logging

from .schema import Profile, SkillGap, SkillGapRequest, SkillGapResponse
from .analyzer import get_analyzer, SkillGapAnalyzer, ROLE_SKILL_TEMPLATES

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/skillgap",
    tags=["skill-gap"],
    responses={
        400: {"description": "Invalid request"},
        500: {"description": "Internal server error"},
    }
)


@router.post("/analyze", response_model=SkillGapResponse)
async def analyze_skill_gap_endpoint(request: SkillGapRequest) -> SkillGapResponse:
    """
    Analyze skill gaps for a user profile against a target role.
    
    **Request:**
    ```json
    {
        "profile": {
            "user_id": "user_123",
            "skills": [
                {"name": "JavaScript", "proficiency": "advanced"},
                {"name": "React", "proficiency": "advanced"}
            ]
        },
        "target_role": "Senior Frontend Engineer",
        "include_market_data": false
    }
    ```
    
    **Response:**
    ```json
    {
        "success": true,
        "skill_gap": {
            "target_role": "Senior Frontend Engineer",
            "match_percentage": 50.0,
            "critical_gaps_count": 0,
            "skill_gaps": [
                {
                    "skill_name": "TypeScript",
                    "priority": "high",
                    "gap_reason": "Not held by user, highly demanded"
                }
            ]
        }
    }
    ```
    
    Args:
        request: SkillGapRequest containing profile and target role
    
    Returns:
        SkillGapResponse with analysis results or errors
    
    Raises:
        HTTPException: If analysis fails
    """
    try:
        # Validate request
        if not request.profile or not request.target_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile and target_role are required"
            )
        
        # Perform analysis
        analyzer = get_analyzer()
        skill_gap = analyzer.analyze(
            profile=request.profile,
            target_role=request.target_role
        )
        
        logger.info(
            f"Skill gap analysis completed for user {request.profile.user_id}: "
            f"{skill_gap.match_percentage:.1f}% match for {request.target_role}"
        )
        
        return SkillGapResponse(
            success=True,
            skill_gap=skill_gap
        )
    
    except ValueError as e:
        logger.error(f"Validation error in skill gap analysis: {str(e)}")
        return SkillGapResponse(
            success=False,
            errors=[str(e)]
        )
    
    except Exception as e:
        logger.error(f"Unexpected error in skill gap analysis: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during skill gap analysis"
        )


@router.get("/roles", response_model=dict)
async def get_available_roles() -> dict:
    """
    Get list of available target roles and their required skills.
    
    Useful for the UI to populate dropdown/autocomplete for target roles.
    
    **Response:**
    ```json
    {
        "roles": [
            {
                "role": "Junior Frontend Developer",
                "required_skills": ["JavaScript", "HTML", "CSS", "React"],
                "skill_count": 4
            },
            {
                "role": "Senior Frontend Engineer",
                "required_skills": ["JavaScript", "React", "TypeScript", ...],
                "skill_count": 7
            }
        ],
        "total_roles": 8
    }
    ```
    
    Returns:
        Dictionary with available roles and their required skills
    """
    try:
        analyzer = get_analyzer()
        roles_data = []
        
        for role, skill_tuples in analyzer.role_templates.items():
            skill_names = [skill for skill, _, _ in skill_tuples]
            roles_data.append({
                "role": role,
                "required_skills": skill_names,
                "skill_count": len(skill_names)
            })
        
        return {
            "success": True,
            "roles": sorted(roles_data, key=lambda x: x["role"]),
            "total_roles": len(roles_data)
        }
    
    except Exception as e:
        logger.error(f"Error fetching available roles: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching available roles"
        )


@router.post("/compare-profiles", response_model=dict)
async def compare_profiles(
    profile1: Profile,
    profile2: Profile,
    target_role: str
) -> dict:
    """
    Compare skill gaps for two profiles against the same target role.
    
    Useful for showing how two users compare in their readiness for a role.
    
    Args:
        profile1: First profile to analyze
        profile2: Second profile to analyze
        target_role: Target role to analyze against
    
    Returns:
        Comparison of gaps and match percentages
    """
    try:
        analyzer = get_analyzer()
        
        gap1 = analyzer.analyze(profile1, target_role)
        gap2 = analyzer.analyze(profile2, target_role)
        
        return {
            "success": True,
            "target_role": target_role,
            "profile1": {
                "match_percentage": gap1.match_percentage,
                "critical_gaps": gap1.critical_gaps_count,
                "total_gaps": len(gap1.skill_gaps)
            },
            "profile2": {
                "match_percentage": gap2.match_percentage,
                "critical_gaps": gap2.critical_gaps_count,
                "total_gaps": len(gap2.skill_gaps)
            },
            "better_match": "profile1" if gap1.match_percentage >= gap2.match_percentage else "profile2",
            "difference": abs(gap1.match_percentage - gap2.match_percentage)
        }
    
    except Exception as e:
        logger.error(f"Error comparing profiles: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while comparing profiles"
        )


@router.get("/health", response_model=dict)
async def health_check() -> dict:
    """
    Health check endpoint for the skill-gap service.
    
    Returns:
        Status of the skill-gap analyzer
    """
    try:
        analyzer = get_analyzer()
        return {
            "status": "healthy",
            "service": "skillgap",
            "roles_available": len(analyzer.role_templates),
            "canonical_skills": len(analyzer.taxonomy.canonical_skills)
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return {
            "status": "unhealthy",
            "service": "skillgap",
            "error": str(e)
        }


# Export router for FastAPI app integration
__all__ = ["router"]
