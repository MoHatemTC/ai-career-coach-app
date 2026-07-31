"""THE MOCK BOUNDARY — the one file to replace when the last stage lands.

What is real vs mocked in this UI
---------------------------------
REAL   : CV upload and parsing (POSTs to the backend's /upload endpoint, which
         runs the actual CV parser), the editable profile form, notification
         settings (persisted to SQLite via /notifications/*), and — as of the
         integration work — job retrieval and ranking, which now go to the real
         `POST /matching/pipeline`: Menna's Qdrant vector search followed by
         Ramez's LLM re-ranker.
MOCKED : only the per-job *explanation*. The Match Explanation Agent is now
         on main (`backend/services/match_explanation_agent.py`, merged by
         PR #17) but is not yet wired into the pipeline, because it needs
         inputs the retrieval payload does not carry: a `JobInfo` with
         `required_skills`, and a `MatchResult` with matched/missing skills
         from the skill-gap analyser. Until that join is built,
         `placeholder_explanation` below stands in for it.

The remaining mock is deliberately inert. It does not invent strengths, gaps
or recommendations about the candidate — fabricated analysis is worse than
none, because it looks exactly like the real thing. It reports only numbers
the pipeline genuinely produced (the retriever's similarity and the
re-ranker's fit score) and says plainly that the reasoning is missing.

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

The nested `explanation` is field-for-field identical to the real
`MatchExplanation` (verified against `backend/services/match_explanation_agent.py`,
now on main), so once the agent is fed its inputs, wiring it in means replacing
`placeholder_explanation` with `match_explanation.model_dump()` and nothing else.

Job title and company sit *outside* `explanation` because the real
`MatchExplanation` carries no job identity — it only explains an
already-computed match. That identity comes from the retrieval step (the Qdrant
payload carries `title` and `company`; see docs/vector-store.md).

Do not change either shape without updating `render_match_card` in
chatbot_ui.py at the same time.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_client  # noqa: E402

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


def placeholder_explanation(entry: Dict[str, Any]) -> Dict[str, Any]:
    """MOCK: stands in for the Match Explanation Agent until it is wired in.

    Reports only what the pipeline actually computed. The list fields stay
    empty on purpose: the agent that produces that reasoning is not fed its
    inputs yet, and filling them with plausible-looking text would present
    invented claims about the candidate as analysis.
    """
    job = entry.get("job_data") or {}
    fit = entry.get("fit_score")
    similarity = job.get("match_score")

    measured = []
    if fit is not None:
        measured.append(f"re-ranker fit score {fit}")
    if similarity is not None:
        measured.append(f"vector similarity {round(float(similarity), 3)}")
    measured_text = ", ".join(measured) if measured else "no scores reported"

    return {
        "overall_alignment_summary": (
            f"Retrieved and ranked ({measured_text}). "
            "Written explanation is not available yet. The Match Explanation "
            "Agent is not wired in, so no strengths or gaps have been analysed."
        ),
        "strengths": [],
        "gaps_or_missing_requirements": [],
        "recommendations": [],
        "next_steps": [],
    }


def run_matching_pipeline(profile: Dict, top_k: int = 10) -> List[Dict]:
    """Retrieve and rank jobs for `profile`, then attach explanations.

    Stages 1 and 2 are REAL — this calls `POST /matching/pipeline`, which runs
    Qdrant retrieval and LLM re-ranking backend-side. Stage 3 is the mock
    above.

    Raises `api_client.BackendError` if the backend is unreachable or the
    pipeline fails; the caller shows that to the user rather than rendering an
    empty result that looks like "no matches".

    Args:
        profile: the confirmed profile dict from the UI form.
        top_k: how many candidates retrieval considers before re-ranking.

    Returns:
        A list of dicts with the keys in `MATCH_RESULT_KEYS`, whose
        `explanation` value has the keys in `EXPLANATION_KEYS`.
    """
    ranked = api_client.run_match_pipeline(profile, top_k=top_k)

    results = []
    for entry in ranked:
        job = entry.get("job_data") or {}
        # The backend attaches a real MatchExplanation. The placeholder is now
        # a fallback for the one case the backend cannot explain: a ranked job
        # that is missing from SQLite, where inventing requirements would be
        # the only alternative.
        explanation = entry.get("explanation") or placeholder_explanation(entry)
        results.append(
            {
                "job_title": job.get("title") or "Untitled role",
                "company": job.get("company") or "Unknown company",
                "location": job.get("location"),
                "description": job.get("description"),
                "required_skills": job.get("required_skills") or [],
                "url": job.get("url"),
                "explanation": explanation,
            }
        )
    return results
