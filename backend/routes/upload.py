from backend.services.llm_service import extract_profile
from fastapi import APIRouter, UploadFile, File
from backend.services.cv_parser import extract_text
import os
import shutil

router = APIRouter()

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@router.post("/upload")
async def upload_cv(file: UploadFile = File(...)):

    # Save uploaded file
    file_location = os.path.join(UPLOAD_FOLDER, file.filename)

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

   # Extract text
    extracted_text = extract_text(file_location)

    # Extract structured profile using the LLM
    profile = extract_profile(extracted_text)

    return {
        "message": "CV processed successfully!",
        "filename": file.filename,
        "profile": profile
    }