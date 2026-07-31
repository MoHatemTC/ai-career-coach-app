from sentence_transformers import util

from backend.features.matching.vector_store import get_embedding_model
from backend.models.job import JobPosting
from backend.models.profile import Profile


def get_model():
    """The shared embedding model, loaded lazily on first use.

    Delegates to the vector store's loader rather than constructing a second
    SentenceTransformer. Two instances would mean two copies of the weights in
    memory and, worse, a second place for the model choice to drift away from
    the frozen embedding contract.
    """
    return get_embedding_model()


def calculate_match_score(profile: Profile, job: JobPosting) -> float:
    """Cosine similarity between a profile's skills and a job's, as 0-100.

    `job` is the canonical `backend.models.job.JobPosting` — the same object
    `orm_to_job_posting` returns, which is what the only caller (the fallback
    path in `routes.py`) actually passes. Reading `job.required_skills` here
    raised AttributeError on every request that reached the fallback.
    """
    profile_text = " ".join(profile.skills) if profile.skills else ""
    job_text = ", ".join(job.skills) if job.skills else ""
    if not profile_text.strip() or not job_text.strip():
        return 0.0

    try:
        model = get_model()
        profile_embedding = model.encode(profile_text, convert_to_tensor=True)
        job_embedding = model.encode(job_text, convert_to_tensor=True)

        similarity = util.cos_sim(profile_embedding, job_embedding).item()

        score = float(similarity) * 100.0
        return round(score, 2)
    except Exception:
        return 0.0
