from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.profile import Profile
from backend.schemas.profile import ProfileUpdate
import json

router = APIRouter()


@router.get("/profiles")
def get_profiles():
    db: Session = SessionLocal()

    profiles = db.query(Profile).all()

    result = []
    for profile in profiles:
        result.append({
            "id": profile.id,
            "name": profile.name,
            "email": profile.email,
            "phone": profile.phone,
            "headline": profile.headline,
            "location": profile.location,
            "skills": json.loads(profile.skills),
            "education": json.loads(profile.education),
            "experience": json.loads(profile.experience),
            "summary": profile.summary
        })

    db.close()
    return result


@router.get("/profile/{profile_id}")
def get_profile(profile_id: int):
    db: Session = SessionLocal()

    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    db.close()

    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "headline": profile.headline,
        "location": profile.location,
        "skills": json.loads(profile.skills),
        "education": json.loads(profile.education),
        "experience": json.loads(profile.experience),
        "summary": profile.summary
    }


@router.put("/profile/{profile_id}")
def update_profile(profile_id: int, updated_data: ProfileUpdate):
    db: Session = SessionLocal()

    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if profile is None:
        db.close()
        raise HTTPException(status_code=404, detail="Profile not found")

    data = updated_data.model_dump(exclude_unset=True)

    if "name" in data:
        profile.name = data["name"]

    if "email" in data:
        profile.email = data["email"]

    if "phone" in data:
        profile.phone = data["phone"]

    if "headline" in data:
        profile.headline = data["headline"]

    if "location" in data:
        profile.location = data["location"]

    if "summary" in data:
        profile.summary = data["summary"]

    if "skills" in data:
        profile.skills = json.dumps(data["skills"])

    if "education" in data:
        profile.education = json.dumps(data["education"])

    if "experience" in data:
        profile.experience = json.dumps(data["experience"])

    db.commit()
    db.refresh(profile)
    db.close()

    return {
        "message": "Profile updated successfully",
        "profile_id": profile.id
    }