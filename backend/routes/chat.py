from fastapi import APIRouter

from backend.schemas.chat import ChatRequest
from backend.services.conversational_agent import process_user_message

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("")
def chat(request: ChatRequest):

    return process_user_message(
        request.message,
        request.profile
    )