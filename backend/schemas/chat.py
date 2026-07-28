from typing import Any, Dict
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    profile: Dict[str, Any]


class ChatResponse(BaseModel):
    intent: str
    reply: str
    updated_profile: Dict[str, Any]
    run_pipeline: bool