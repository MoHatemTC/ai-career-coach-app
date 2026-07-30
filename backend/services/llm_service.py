"""CV parsing: turn extracted CV text into a structured profile.

Goes through `backend.services.llm_client`, the shared provider switch, rather
than constructing its own Gemini client. That means CV parsing uses whichever
provider `AI_PROVIDER` selects (the LiteLLM gateway by default) instead of a
separate, heavily rate-limited Gemini key.
"""

import json

from dotenv import load_dotenv

from backend.services.llm_client import complete_with_reason

load_dotenv()


def extract_profile(cv_text: str):
    prompt = f"""
You are an expert CV parser.

Extract the following information from the CV.

Return ONLY valid JSON.

The JSON format must be:

{{
    "name": "",
    "email": "",
    "phone": "",
    "skills": [],
    "education": [],
    "experience": []
}}

CV:

{cv_text}
"""

    content, reason = complete_with_reason(
        prompt, response_mime_type="application/json"
    )
    if content is None:
        raise RuntimeError(f"The CV parser's LLM call failed: {reason}")
    content = content.strip()

    # Remove markdown if Gemini returns ```json ... ```
    if content.startswith("```"):
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

    return json.loads(content)