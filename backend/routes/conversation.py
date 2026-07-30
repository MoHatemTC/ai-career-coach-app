"""HTTP route for the career-coach chat.

Thin layer only; the logic is in `backend/services/conversation.py`.

Serves the same contract as the CV lane's `POST /chat`, so the UI can prefer
that endpoint when it exists and fall back here otherwise without any change to
how it handles the response.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.conversation import respond

router = APIRouter(prefix="/conversation", tags=["Conversation"])


class Turn(BaseModel):
    role: str
    content: str


class ConversationRequest(BaseModel):
    message: str
    # The profile is free-form: it is the CV parser's output after the user has
    # edited it, not a validated model. Requiring a schema here would mean
    # inventing fields the parser never produced.
    profile: Dict[str, Any] = Field(default_factory=dict)
    history: Optional[List[Turn]] = None


class ConversationResponse(BaseModel):
    intent: str
    reply: str
    updated_profile: Dict[str, Any]
    run_pipeline: bool


@router.post("", response_model=ConversationResponse)
def converse(request: ConversationRequest) -> ConversationResponse:
    """Reply to a chat message, possibly editing the profile or starting a run.

    Never raises for "the model misbehaved" reasons: the service degrades to a
    deterministic reply that still routes a request for matches correctly, so a
    missing key or an overloaded model cannot take the chat down.
    """
    result = respond(
        request.message,
        request.profile,
        [turn.model_dump() for turn in (request.history or [])],
    )
    return ConversationResponse(
        intent=result["intent"],
        reply=result["reply"],
        updated_profile=result["updated_profile"],
        run_pipeline=result["run_pipeline"],
    )
