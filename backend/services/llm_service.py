import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("models/gemini-flash-latest")
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

    response = model.generate_content(prompt)

    content = response.text.strip()

    # Remove markdown if Gemini returns ```json ... ```
    if content.startswith("```"):
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

    return json.loads(content)