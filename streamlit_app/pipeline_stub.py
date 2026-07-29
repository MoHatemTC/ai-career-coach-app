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
one function — `run_matching_pipeline` below — and nothing in the UI.

Return shape (the contract)
---------------------------
Each result pairs a job's identity with its explanation:

    {
        "job_title": str,
        "company": str,
        "explanation": {          # mirrors MatchExplanation exactly
            "overall_alignment_summary": str,
            "strengths": [str],
            "gaps_or_missing_requirements": [str],
            "recommendations": [str],
            "next_steps": [str],
        },
    }

The nested `explanation` is deliberately field-for-field identical to the real
`MatchExplanation` model (`backend/services/match_explanation_agent.py` on the
match-explanation branch), so the real object can be dropped in with
`explanation=match_explanation.model_dump()` and nothing else changes.

Job title and company sit *outside* `explanation` because the real
`MatchExplanation` carries no job identity at all — it only explains an
already-computed `MatchResult`. That identity has to come from the retrieval
step (the Qdrant payload already carries `title` and `company`; see
docs/vector-store.md), so the UI keeps them as separate top-level fields
rather than expecting the explanation agent to supply them.

Do not change either shape without updating `render_match_card` in
chatbot_ui.py at the same time.
"""

from typing import Dict, List

# Top-level keys every result must have. The UI checks these, so a shape
# mismatch surfaces as a visible warning instead of blank cards.
MATCH_RESULT_KEYS = ("job_title", "company", "explanation")

# Keys of the nested explanation — field-for-field the real MatchExplanation.
EXPLANATION_KEYS = (
    "overall_alignment_summary",
    "strengths",
    "gaps_or_missing_requirements",
    "recommendations",
    "next_steps",
)


def run_matching_pipeline(profile: Dict) -> List[Dict]:
    """MOCK — replace internals with real Menna->Ramez->Farag calls once
    available; do not change the return shape without updating the UI render
    function too.

    Real implementation, when it exists, will roughly be:
        1. Menna:  embed `profile` and search the Qdrant `job_postings`
                   collection (see docs/vector-store.md) -> candidate jobs.
                   Job title/company come from the hit payload here.
        2. Ramez:  rank/score those candidates -> a MatchResult per job
        3. Farag:  generate_match_explanation(...) -> MatchExplanation, which
                   becomes the `explanation` dict via .model_dump()

    Args:
        profile: the confirmed profile dict from the UI form — currently
            unused by the mock, but it is passed through so the signature
            does not change when the real chain is wired in.

    Returns:
        A list of dicts with the keys in `MATCH_RESULT_KEYS`, whose
        `explanation` value has the keys in `EXPLANATION_KEYS`.
    """
    # --- MOCK DATA BELOW — none of this calls any real service -------------
    return [
        {
            "job_title": "Senior Backend Engineer",
            "company": "TechMena Hub",
            "explanation": {
                "overall_alignment_summary": (
                    "Strong overall fit. Your core backend stack matches the "
                    "role's stated requirements closely, with one "
                    "infrastructure gap that is realistic to close."
                ),
                "strengths": [
                    "Python and FastAPI both appear in your profile and are listed as required.",
                    "Your ingestion-pipeline experience maps to the data-plumbing half of this role.",
                ],
                "gaps_or_missing_requirements": [
                    "Kubernetes experience is required but not listed on your profile.",
                    "No evidence of production on-call ownership.",
                ],
                "recommendations": [
                    "Apply — lead with the ingestion-pipeline work.",
                    "Mention container experience even if it is Docker rather than Kubernetes.",
                ],
                "next_steps": [
                    "Add any container or deployment work to your CV before applying.",
                    "Prepare one concrete example of debugging a production data issue.",
                ],
            },
        },
        {
            "job_title": "Data Platform Engineer",
            "company": "Desert AI",
            "explanation": {
                "overall_alignment_summary": (
                    "Good partial fit. The ETL responsibilities line up well, "
                    "but the role expects distributed compute you have not "
                    "shown yet."
                ),
                "strengths": [
                    "Your data pipeline experience maps directly onto the ETL responsibilities.",
                    "SQL and schema-design work is directly relevant.",
                ],
                "gaps_or_missing_requirements": [
                    "Spark at scale is expected; your profile shows batch processing only.",
                    "No distributed-compute or cluster experience listed.",
                ],
                "recommendations": [
                    "Worth applying, but expect Spark questions.",
                    "Frame your batch work in terms of data volume and throughput.",
                ],
                "next_steps": [
                    "Build a small Spark project so you have something concrete to discuss.",
                    "Review partitioning and shuffle basics before an interview.",
                ],
            },
        },
        {
            "job_title": "Python Developer",
            "company": "Cairo Software House",
            "explanation": {
                "overall_alignment_summary": (
                    "You clear the bar comfortably — the requirements are a "
                    "subset of what you already have. The question is whether "
                    "the seniority is right, not whether you qualify."
                ),
                "strengths": [
                    "Every listed requirement is already on your profile.",
                    "No technical gap to close for this role.",
                ],
                "gaps_or_missing_requirements": [
                    "Likely below your seniority; the posting targets 1-3 years of experience.",
                ],
                "recommendations": [
                    "Only apply if you specifically want a lateral move.",
                    "Otherwise filter for more senior postings.",
                ],
                "next_steps": [
                    "Check whether the team has a senior track before investing time.",
                ],
            },
        },
    ]
