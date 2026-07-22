from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_rank_jobs_endpoint():
    payload = {
        "profile": {
            "user_id": "user_1",
            "name": "Menna",
            "current_title": "Backend Developer",
            "skills": ["python", "fastapi"],
            "experience_years": 2,
            "summary": "Python developer with experience in building web APIs.",
            "location": "Cairo",
            "preferred_work_type": "Full-time",
            "salary_expectation": 14000
        }
    }
    
    response = client.post("/matching/rank-jobs", json=payload)
    assert response.status_code == 200