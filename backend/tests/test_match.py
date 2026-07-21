from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_matching_endpoint():
    payload = {
        "job": {
            "job_id": "job_123",
            "title": "Python Developer",
            "required_skills": ["python", "fastapi"],
            "min_experience": 2,
            "description": "Amazing job opportunity",
            "location": "Cairo",
            "work_type": "Full-time",
            "salary": 15000
        },
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
    
    response = client.post("/matching/match", json=payload)
    
    if response.status_code == 422:
        print("\n--- ERROR DETAILS ---")
        print(response.json())
        print("---------------------\n")
        
    assert response.status_code == 200