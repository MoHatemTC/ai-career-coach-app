from openai import OpenAI
import json


client = OpenAI()

def create_llm(profile , menna_jobs):
    

    jobs_json = json.dumps(m_response, ensure_ascii=False)

    messages  = [
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
    1. Relevance to user query
    2. Required skills match
    3. Job title similarity
    4. Experience level match
    
    for example
    Output format:
    {
      "top_3": [
        {
          "job_id": "job_5521",
          "rank": 1,
          "fit_score": 0.91,
          "job_data": {
            "job_id": "job_5521",
            "title": "Junior Data Analyst",
            "company": "Acme Corp",
            "location": "Cairo, Egypt",
            "description": "We're looking for a junior data analyst to support reporting and dashboarding...",
            "required_skills": ["SQL", "Excel", "Power BI"],
            "salary_range": { "min": 9000, "max": 13000, "currency": "EGP" },
            "source": "wuzzuf",
            "url": "https://wuzzuf.net/jobs/p/job_5521",
            "date_posted": "2026-07-10"
        },
        {
          "job_id": "job_5521",
          "rank": 2,
          "fit_score": 0.91,
          "job_data": {
            "job_id": "job_5521",
            "title": "Junior Data Analyst",
            "company": "Acme Corp",
            "location": "Cairo, Egypt",
            "description": "We're looking for a junior data analyst to support reporting and dashboarding...",
            "required_skills": ["SQL", "Excel", "Power BI"],
            "salary_range": { "min": 9000, "max": 13000, "currency": "EGP" },
            "source": "wuzzuf",
            "url": "https://wuzzuf.net/jobs/p/job_5521",
            "date_posted": "2026-07-10"
        },
        {
         "job_id": "job_5521",
          "rank": 3,
          "fit_score": 0.91,
          "job_data": {
            "job_id": "job_5521",
            "title": "Junior Data Analyst",
            "company": "Acme Corp",
            "location": "Cairo, Egypt",
            "description": "We're looking for a junior data analyst to support reporting and dashboarding...",
            "required_skills": ["SQL", "Excel", "Power BI"],
            "salary_range": { "min": 9000, "max": 13000, "currency": "EGP" },
            "source": "wuzzuf",
            "url": "https://wuzzuf.net/jobs/p/job_5521",
            "date_posted": "2026-07-10"
        }
      ]
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


    response = client.chat.completions.create(
            model="gpt-5.5",
            messages=messages
        )
    
    content = response.choices[0].message.content
    
    data = json.loads(content) # parse llm response from text to json
    try:
      data = json.loads(content)
    except json.JSONDecodeError:
      raise Exception("Invalid JSON from LLM")
    return data
    







    



