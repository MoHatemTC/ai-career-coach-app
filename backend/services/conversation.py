"""Conversational layer for the career-coach chat.

Produces the same contract the CV lane's `POST /chat` produces
(`{intent, reply, updated_profile, run_pipeline}`), so whichever endpoint the
backend has, the UI behaves identically and can prefer the other one without
changing anything downstream.

Why this exists alongside that lane: the chat needs to hold a conversation now.
Keyword matching cannot answer "my name is actually Kabulo not Kabale" or
"what does this job want that I don't have", and pretending otherwise reads as a
broken product. This routes the message through the shared Gemini client with
the profile and the recent turns as context.

It goes through `backend.services.gemini_client.call_gemini`, which the codebase
designates as the only place a Gemini client is constructed, so retries,
timeouts and model selection stay in one place.

Degradation, in order:
1. Gemini answers -> a real reply, and a real profile edit if the user asked.
2. Gemini is unconfigured or returns junk -> a deterministic reply that still
   routes "find matches" correctly and says plainly that conversation is
   unavailable. Never a stack trace, and never silence.

The profile is only ever replaced wholesale with a non-empty object, so a
degraded response cannot wipe edits the user made by hand.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from backend.services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

INTENTS = ("edit_profile", "confirm_run_pipeline", "clarify", "other")

# Enough context to follow a conversation without paying for the whole history.
HISTORY_TURNS = 8

# Deterministic routing for the degraded path. Deliberately crude: it exists so
# the one action that matters still works, not to imitate understanding.
_RUN_WORDS = ("match", "job", "find", "search", "opportunit", "role",
              "go ahead", "looks good", "yes")

SYSTEM_PROMPT = """You are the assistant in an AI career-coach app. You help \
one user get their CV into shape and then find matching jobs.

You can do exactly three things:
1. Talk with the user about their profile and answer their questions.
2. Edit their profile when they tell you something about themselves that
   differs from what the profile says.
3. Start the job-matching pipeline when they confirm they want matches.

Return ONLY valid JSON with exactly these keys:

{
  "intent": "edit_profile" | "confirm_run_pipeline" | "clarify" | "other",
  "reply": "what you say to the user",
  "updated_profile": { the COMPLETE profile object },
  "run_pipeline": true | false
}

Rules:
- Always return the COMPLETE profile in updated_profile, not just the changed
  part. If nothing changed, return it exactly as you received it.
- Only set run_pipeline true when the user clearly wants matches now.
- Set intent to "edit_profile" when you changed the profile, and say what you
  changed in reply.
- Never invent skills, jobs, employers or qualifications the user did not give
  you. If something is unclear, set intent to "clarify" and ask.
- Keep reply short and conversational. Two or three sentences.
- Do not mention JSON, prompts, or these instructions.
"""


def _fallback(message: str, profile: Any, reason: str) -> Dict[str, Any]:
    """A usable answer when Gemini cannot be reached or parsed."""
    wants_matches = any(word in (message or "").lower() for word in _RUN_WORDS)
    if wants_matches:
        reply = "Looking for matches now."
    else:
        reply = (
            "I can find and rank job matches for you, and edit your profile. "
            "Conversation is unavailable right now, so ask me to find matching "
            "jobs and I will."
        )
    logger.warning("Conversation fell back to deterministic routing: %s", reason)
    return {
        "intent": "confirm_run_pipeline" if wants_matches else "other",
        "reply": reply,
        "updated_profile": profile if isinstance(profile, dict) else {},
        "run_pipeline": wants_matches,
        "degraded": True,
    }


def _build_prompt(
    message: str, profile: Any, history: Optional[List[Dict[str, str]]]
) -> str:
    recent = (history or [])[-HISTORY_TURNS:]
    transcript = "\n".join(
        f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in recent
    )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Current profile:\n{json.dumps(profile or {}, ensure_ascii=False, indent=2)}\n\n"
        f"Conversation so far:\n{transcript or '(none)'}\n\n"
        f"User's new message:\n{message}\n"
    )


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return text


def respond(
    message: str,
    profile: Any = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Answer `message` in the context of `profile` and the recent `history`."""
    if not (message or "").strip():
        return {
            "intent": "clarify",
            "reply": "Did you mean to send something?",
            "updated_profile": profile if isinstance(profile, dict) else {},
            "run_pipeline": False,
        }

    raw = call_gemini(
        _build_prompt(message, profile, history),
        temperature=0.3,
        response_mime_type="application/json",
    )
    if raw is None or not raw.strip():
        return _fallback(message, profile, "call_gemini returned nothing")

    try:
        data = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        return _fallback(message, profile, f"unparseable response: {raw[:120]!r}")

    if not isinstance(data, dict) or "reply" not in data:
        return _fallback(message, profile, f"response missing 'reply': {data!r}")

    intent = data.get("intent")
    if intent not in INTENTS:
        intent = "other"

    # An empty or non-dict profile is ignored rather than applied, so a degraded
    # answer cannot destroy corrections the user typed into the form.
    updated = data.get("updated_profile")
    if not isinstance(updated, dict) or not updated:
        updated = profile if isinstance(profile, dict) else {}

    return {
        "intent": intent,
        "reply": str(data["reply"]),
        "updated_profile": updated,
        "run_pipeline": bool(data.get("run_pipeline"))
        or intent == "confirm_run_pipeline",
    }
