from fastapi import APIRouter, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.profile import Profile
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
def update_profile(profile_id: int, updated_data: dict = Body(...)):
    db: Session = SessionLocal()

    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if profile is None:
        db.close()
        raise HTTPException(status_code=404, detail="Profile not found")

    if "name" in updated_data:
        profile.name = updated_data["name"]

    if "email" in updated_data:
        profile.email = updated_data["email"]

    if "phone" in updated_data:
        profile.phone = updated_data["phone"]

    if "headline" in updated_data:
        profile.headline = updated_data["headline"]

    if "location" in updated_data:
        profile.location = updated_data["location"]

    if "summary" in updated_data:
        profile.summary = updated_data["summary"]

    if "skills" in updated_data:
        profile.skills = json.dumps(updated_data["skills"])

    if "education" in updated_data:
        profile.education = json.dumps(updated_data["education"])

    if "experience" in updated_data:
        profile.experience = json.dumps(updated_data["experience"])

    db.commit()
    db.refresh(profile)
    db.close()

    return {
        "message": "Profile updated successfully",
        "profile_id": profile.id
    }