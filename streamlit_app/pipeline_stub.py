"""THE MOCK BOUNDARY — the one file to replace when the real chain lands.

What is real vs mocked in this UI
---------------------------------
REAL   : CV upload and parsing (POSTs to the backend's /upload endpoint, which
         runs the actual CV parser), the editable profile form, and the
         notification settings (persisted to SQLite via /notifications/*).
MOCKED : everything in this file — the matching chain. `run_matching_pipeline`
         returns hardcoded results instead of calling
         Menna (vector retrieval) -> Ramez (ranking) -> Farag (explanations).

The point of this split is that wiring in the real chain should touch exactly
one function — `run_matching_pipeline` below — and nothing in the UI. The
return shape is therefore the contract: a list of dicts shaped like Farag's
`MatchExplanation` (job_title, company, strength, weakness, recommendation).
Keep that shape when you swap the internals, or update
`render_match_card` in chatbot_ui.py at the same time.
"""

from typing import Dict, List

# The keys every result dict must have. The UI renders exactly these, so this
# doubles as the contract check when the real implementation lands.
MATCH_RESULT_KEYS = (
    "job_title",
    "company",
    "strength",
    "weakness",
    "recommendation",
)


def run_matching_pipeline(profile: Dict) -> List[Dict]:
    """MOCK — replace internals with real Menna->Ramez->Farag calls once
    available; do not change the return shape without updating the UI render
    function too.

    Real implementation, when it exists, will roughly be:
        1. Menna:  embed `profile` and search the Qdrant `job_postings`
                   collection (see docs/vector-store.md) -> candidate jobs
        2. Ramez:  rank/score those candidates against the profile
        3. Farag:  generate a MatchExplanation per ranked job

    Args:
        profile: the confirmed profile dict from the UI form — currently
            unused by the mock, but it is passed through so the signature
            does not change when the real chain is wired in.

    Returns:
        A list of dicts, each with the keys in `MATCH_RESULT_KEYS`.
    """
    # --- MOCK DATA BELOW — none of this calls any real service -------------
    return [
        {
            "job_title": "Senior Backend Engineer",
            "company": "TechMena Hub",
            "strength": (
                "Strong overlap on core backend skills — Python and FastAPI "
                "both appear in your profile and are listed as required."
            ),
            "weakness": (
                "The posting asks for Kubernetes experience, which is not "
                "listed on your profile."
            ),
            "recommendation": (
                "Apply. Lead with your ingestion-pipeline work, and mention any "
                "container experience even if it is Docker rather than Kubernetes."
            ),
        },
        {
            "job_title": "Data Platform Engineer",
            "company": "Desert AI",
            "strength": (
                "Your data pipeline experience maps directly onto the ETL "
                "responsibilities in this role."
            ),
            "weakness": (
                "Role expects Spark at scale; your profile shows batch "
                "processing but no distributed compute."
            ),
            "recommendation": (
                "Worth applying. Consider a short Spark tutorial project first "
                "so you have something concrete to discuss."
            ),
        },
        {
            "job_title": "Python Developer",
            "company": "Cairo Software House",
            "strength": (
                "Requirements are a subset of skills you already have — you "
                "comfortably clear the bar."
            ),
            "weakness": (
                "Likely below your seniority; the posting targets 1-3 years "
                "of experience."
            ),
            "recommendation": (
                "Only apply if you want a lateral move. Otherwise filter for "
                "more senior postings."
            ),
        },
    ]
