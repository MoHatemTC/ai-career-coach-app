import json

from backend.database import SessionLocal
from backend.models.profile import Profile


def save_profile(profile_data):
    db = SessionLocal()

    profile = Profile(
        name=profile_data.get("name", ""),
        email=profile_data.get("email", ""),
        phone=profile_data.get("phone", ""),
        headline=profile_data.get("headline", ""),
        location=profile_data.get("location", ""),
        skills=json.dumps(profile_data.get("skills", [])),
        education=json.dumps(profile_data.get("education", [])),
        experience=json.dumps(profile_data.get("experience", [])),
        summary=profile_data.get("summary", "")
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.close()

    return profile