from sentence_transformers import SentenceTransformer, util

from backend.features.matching.vector_store import EMBEDDING_MODEL_NAME
from backend.models.job import JobPosting
from backend.models.profile import Profile

_model = None


def get_model() -> SentenceTransformer:
    """Load the shared embedding model once, on first use.

    Loaded lazily rather than at import time so that importing this module —
    which `backend.main` does transitively, on every startup and every pytest
    collection — does not pull ~90MB of model weights. The model name comes
    from the vector-store contract so the reader and writer cannot drift.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


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
