import json
import os

import google.generativeai as genai
from dotenv import load_dotenv

from backend.schemas.chat import ChatResponse

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("models/gemini-flash-latest")


def process_user_message(message: str, profile: dict):
    prompt = f"""
You are the conversational agent for an AI Career Coach.

Current Profile:
{json.dumps(profile, indent=4)}

User Message:
"{message}"

Determine the user's intent.

Possible intents:
- edit_profile
- confirm_run_pipeline
- clarify
- other

Rules:
1. Always return the COMPLETE profile.
2. If editing, modify only the requested fields.
3. If there is no edit, return the original profile unchanged.
4. If the user confirms ("continue", "looks good", "yes", "proceed"),
   set:
   intent = "confirm_run_pipeline"
   run_pipeline = true
5. If the request is unclear:
   intent = "clarify"
6. Otherwise:
   intent = "other"

Return ONLY valid JSON in this format:

{{
    "intent": "",
    "reply": "",
    "updated_profile": {{
        "name": "",
        "email": "",
        "phone": "",
        "skills": [],
        "education": [],
        "experience": []
    }},
    "run_pipeline": false
}}

Do not return markdown.
"""
    try:
        response = model.generate_content(prompt)
    except Exception:
        return ChatResponse(
            intent="other",
            reply="Sorry, the AI service is currently unavailable. Please try again later.",
            updated_profile=profile,
            run_pipeline=False
        )

    content = response.text.strip()

    if content.startswith("```"):
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        return ChatResponse(
            intent="other",
            reply="Sorry, I couldn't understand your request. Please try again.",
            updated_profile=profile,
            run_pipeline=False
        )

    if "updated_profile" not in result:
        result["updated_profile"] = profile

    if "run_pipeline" not in result:
        result["run_pipeline"] = False

    if "intent" not in result:
        result["intent"] = "other"

    if "reply" not in result:
        result["reply"] = "I'm here to help."

    return ChatResponse(**result)