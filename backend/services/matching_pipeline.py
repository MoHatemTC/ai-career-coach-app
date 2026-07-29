"""End-to-end matching pipeline: vector retrieval, then LLM re-ranking.

Stage 1 (`backend/features/matching/retriever.py`) embeds the profile and
pulls candidates out of the Qdrant `job_postings` collection. Stage 2
(`backend/features/ranking/reranker.py`) re-ranks that shortlist with an LLM.

Stage 3, explanations, is deliberately absent: the Match Explanation Agent is
still on an unmerged branch. The UI attaches placeholder explanations for now
and that is its only remaining mock — see `streamlit_app/pipeline_stub.py`.

Why this lives backend-side rather than in the Streamlit process
----------------------------------------------------------------
`QDRANT_MODE=local` runs Qdrant embedded and takes an *exclusive* lock on its
storage directory (see docs/vector-store.md). While the API server holds that
lock no other process can open the collection, so a UI that queried Qdrant
directly would fail whenever the backend was running. The UI therefore goes
through HTTP, like every other backend call it makes.

Retrieval is left to fail loudly. An empty collection is a legitimate empty
result, but a Qdrant that is down or locked is a real fault, and silently
returning "no matches" for it would look identical to "no jobs matched".
"""

from typing import Any, Dict, List, Optional

from backend.features.matching.retriever import retrieve_top_jobs
from backend.features.ranking.reranker import rerank_jobs

# Free-text profile fields, in the order they are fed to the embedder. The CV
# parser and the UI form use different names for the same thing, so both spellings
# are accepted rather than forcing one lane to rename its fields.
PROFILE_TEXT_FIELDS = (
    "title",
    "current_title",
    "summary",
    "experience",
    "education",
)


def _flatten(value: Any) -> str:
    """Render a profile field as text; the parser returns str or list."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item) for item in value if item)
    return str(value)


def profile_to_text(profile: Any) -> str:
    """Flatten a profile into the text that gets embedded for retrieval.

    Accepts the UI's plain dict or a Pydantic model. Skills are labelled
    because the job side of the collection labels them too — the embedding
    contract in docs/vector-store.md puts skills under a "Skills:" heading, and
    query text that mirrors the indexed text retrieves better.
    """
    if not isinstance(profile, dict):
        profile = (
            profile.model_dump()
            if hasattr(profile, "model_dump")
            else dict(profile)
        )

    parts = [_flatten(profile.get(field)) for field in PROFILE_TEXT_FIELDS]

    skills = profile.get("skills")
    if skills:
        flattened = (
            ", ".join(str(s) for s in skills)
            if isinstance(skills, (list, tuple))
            else str(skills)
        )
        parts.append(f"Skills: {flattened}")

    return "\n".join(part for part in parts if part.strip())


def run_match_pipeline(
    profile: Any,
    top_k: int = 10,
    llm_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Retrieve candidates for `profile`, re-rank them, return the ranking.

    `top_k` is the retrieval width, not the output size — the re-ranker
    narrows to its own top 3. Widening it gives the LLM more to choose from at
    the cost of a longer prompt.

    `llm_client` is injectable so tests can run the whole pipeline without a
    network call.

    Returns the re-ranker's `top_3` list: dicts of
    `{job_id, rank, fit_score, job_data}`. Empty when the profile has no usable
    text or retrieval finds nothing.
    """
    cv_text = profile_to_text(profile)
    if not cv_text.strip():
        return []

    jobs = retrieve_top_jobs(cv_text=cv_text, top_k=top_k)
    if not jobs:
        return []

    ranked = rerank_jobs(profile, jobs, client=llm_client)
    return ranked.get("top_3", [])
