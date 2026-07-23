import json

from backend.database import SessionLocal
from backend.models.profile import Profile


def deduplicate_list(items):
    """
    Remove duplicate strings while preserving order.
    Comparison is case-insensitive.
    """

    if not items:
        return []

    seen = set()
    result = []

    for item in items:
        if not isinstance(item, str):
            continue

        cleaned = item.strip()

        if not cleaned:
            continue

        key = cleaned.lower()

        if key not in seen:
            seen.add(key)
            result.append(cleaned)

    return result


def save_profile(profile_data):
    db = SessionLocal()

    # Deduplicate list fields
    skills = deduplicate_list(profile_data.get("skills", []))
    education = deduplicate_list(profile_data.get("education", []))
    experience = deduplicate_list(profile_data.get("experience", []))

    profile = Profile(
        name=profile_data.get("name", ""),
        email=profile_data.get("email", ""),
        phone=profile_data.get("phone", ""),
        headline=profile_data.get("headline", ""),
        location=profile_data.get("location", ""),
        skills=json.dumps(skills),
        education=json.dumps(education),
        experience=json.dumps(experience),
        summary=profile_data.get("summary", "")
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.close()

    return profile