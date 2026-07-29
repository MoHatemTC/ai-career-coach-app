from google import genai
import json
from retriever import retrieve_top_jobs

client = genai.Client()

def create_llm(profile, jobs):

    jobs_json = json.dumps(jobs, ensure_ascii=False)

    messages = [
        {
            "role": "system",
            "content": """You are an expert job ranking assistant.

Your task:
- Analyze a list of job postings.
- Rank them based on relevance to the user's query.

Strict rules:
- Return ONLY valid JSON.
- No explanations, no extra text.
- Always return exactly top 3 jobs.

Ranking criteria (in order of importance):
1. Relevance to user cv
2. Required skills match
3. Job title similarity
4. Experience level match

Output format:
{
  "top_3": []
}
"""
        },
        {
            "role": "user",
            "content": f"""
User profile:
{profile}

Jobs:
{jobs_json}
"""
        }
    ]


    contents = [
    {
        "role": "user",
        "parts": [
            {
                "text": f"""
You are an expert job ranking assistant.

Return ONLY a valid JSON response.

You MUST strictly follow this exact JSON structure:

{{
  "top_3": [
    {{
      "job_id": "string",
      "rank": number,
      "fit_score": number,
      "job_data": {{
        "job_id": "string",
        "title": "string",
        "company": "string",
        "location": "string",
        "description": "string",
        "skills": ["string"],
        "career_level": ["string"],
        "experience_years": ["string"],
        "salary_range": {{ "min": number, "max": number, "currency": "string" }},
        "source": "string",
        "url": "string",
        "date_posted": "string"
      }}
    }}
  ]
}}

Rules:
- Return exactly 3 items in "top_3"
- Ranks MUST be: 1, 2, 3 (no duplicates)
- fit_score must be between 0 and 1
- Do NOT add any explanation
- Do NOT change keys
- Do NOT add text outside JSON

---

Example Output:

{{
  "top_3": [
    {{
      "job_id": "job_5521",
      "rank": 1,
      "fit_score": 0.91,
      "job_data": {{
        "job_id": "job_5521",
        "title": "Junior Data Analyst",
        "company": "Acme Corp",
        "location": "Cairo, Egypt",
        "description": "We're looking for a junior data analyst...",
        "skills": ["SQL", "Excel", "Power BI"],
        "career_level": ["junior"],
        "experience_years": ["2yrs"],
        "salary_range": {{ "min": 9000, "max": 13000, "currency": "EGP" }},
        "source": "wuzzuf",
        "url": "https://wuzzuf.net/jobs/p/job_5521",
        "date_posted": "2026-07-10"
      }}
    }},
    {{
      "job_id": "job_7782",
      "rank": 2,
      "fit_score": 0.85,
      "job_data": {{ "...": "..." }}
    }},
    {{
      "job_id": "job_9911",
      "rank": 3,
      "fit_score": 0.78,
      "job_data": {{ "...": "..." }}
    }}
  ]
}}

---

User profile:
{profile}

Jobs:
{jobs_json}
"""
            }
        ]
    }
]

    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=contents,
        config={"response_mime_type": "application/json"}
    )

    content = response.text

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise Exception("Invalid JSON from LLM")

    return data


if __name__ == "__main__":
    profile = "your cv text here"
    jobs = retrieve_top_jobs(profile)
    result = create_llm(profile, jobs)
    print(result)