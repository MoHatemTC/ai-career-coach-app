from backend.services.llm_service import extract_profile
from backend.services.profile_service import save_profile
from backend.services.cv_parser import extract_text

from fastapi import APIRouter, UploadFile, File, HTTPException

import os
import shutil
import uuid
import json

router = APIRouter()

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = [".pdf", ".docx"]
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/upload")
async def upload_cv(file: UploadFile = File(...)):

    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are allowed."
        )

    # Validate file size
    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds 5 MB."
        )

    file.file.seek(0)

    # Generate safe filename
    filename = f"{uuid.uuid4()}{ext}"
    file_location = os.path.join(UPLOAD_FOLDER, filename)

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Extract text
        extracted_text = extract_text(file_location)

        # Extract structured profile
        profile = extract_profile(extracted_text)

        # Save profile
        saved_profile = save_profile(profile)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Invalid JSON returned by Gemini."
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    return {
        "message": "CV processed successfully!",
        "filename": filename,
        "profile_id": saved_profile.id,
        "profile": profile
    }