from typing import Any, Dict

from backend.services.llm_service import extract_profile
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from backend.services.cv_parser import extract_text
import os
import shutil

router = APIRouter()


class UploadResponse(BaseModel):
    """Declared so the generated TypeScript client has a shape to work with.

    Without a response_model the OpenAPI schema carries an empty object here,
    and `openapi-typescript` produces nothing usable for the one payload the
    CV screen is built on.

    `profile` stays a loose map on purpose. It is whatever JSON the model
    returned, and the parser cannot promise more than that: education and
    experience come back as plain strings from some models and as objects from
    others. Pinning a stricter shape here would turn a chatty model into a 500
    on a request that actually succeeded. The frontend declares its own
    tolerant view of this and reads it defensively.
    """

    message: str
    filename: str
    profile: Dict[str, Any] = Field(default_factory=dict)

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@router.post("/upload", response_model=UploadResponse)
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