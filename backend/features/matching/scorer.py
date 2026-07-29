from sentence_transformers import SentenceTransformer, util
from backend.models.job_posting import JobPosting
from backend.models.profile import Profile

model = SentenceTransformer('all-MiniLM-L6-v2')

def calculate_match_score(profile: Profile, job: JobPosting) -> float:
    profile_text = " ".join(profile.skills) if profile.skills else ""
    job_text = ", ".join(job.required_skills) if job.required_skills else ""    
    if not profile_text.strip() or not job_text.strip():
        return 0.0

    try:
        profile_embedding = model.encode(profile_text, convert_to_tensor=True)
        job_embedding = model.encode(job_text, convert_to_tensor=True)
        
        similarity = util.cos_sim(profile_embedding, job_embedding).item()
        
        score = float(similarity) * 100.0
        return round(score, 2)
    except Exception:
        return 0.0

def get_model():
    return model