from backend.services.llm_service import extract_profile
from fastapi import APIRouter, HTTPException, UploadFile, File
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

    if not (extracted_text or "").strip():
        # A scanned/image PDF yields nothing: there is no OCR step. Saying so
        # beats sending an empty prompt and returning a blank profile, which is
        # what used to happen and read as "the parser is bad".
        raise HTTPException(
            status_code=422,
            detail=(
                "No text could be extracted from that file. If it is a scanned "
                "image there is no OCR step, so try a text-based PDF or DOCX."
            ),
        )

    # Extract structured profile using the LLM
    try:
        profile = extract_profile(extracted_text)
    except RuntimeError as exc:
        # The LLM was unreachable or misconfigured. That is an upstream outage,
        # not a bug in the request, so it surfaces as 503 with the cause rather
        # than an unhandled 500 and an ASGI traceback.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "message": "CV processed successfully!",
        "filename": file.filename,
        "profile": profile
    }