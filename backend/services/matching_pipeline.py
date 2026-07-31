"""End-to-end matching pipeline: vector retrieval, then LLM re-ranking.

Stage 1 (`backend/features/matching/retriever.py`) embeds the profile and
pulls candidates out of the Qdrant `job_postings` collection. Stage 2
(`backend/features/ranking/reranker.py`) re-ranks that shortlist with an LLM.

Stage 3 (`backend/services/match_explanation_agent.py`) explains each ranked
job. It consumes an already-computed match rather than deriving one, so it
needs inputs the retrieval payload does not carry: a `JobInfo` with
`required_skills`, and a `MatchResult` with matched/missing skills. Those are
assembled here by joining the full posting back from SQLite on `job_id` (which
is in the Qdrant payload precisely so this join is possible) and running the
skill-gap analyser against it.

Nothing in this module recomputes a score. The re-ranker's `fit_score` is the
match, and the explanation agent explains it verbatim.

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

import logging
from typing import Any, Dict, List, Optional

from backend.features.matching.retriever import retrieve_top_jobs
from backend.features.ranking.reranker import rerank_jobs
from backend.models.db_models import JobPostingORM, orm_to_job_posting
from backend.models.job import JobInfo
from backend.models.match_result import MatchResult
from backend.models.profile import Profile
from backend.services.match_explanation_agent import generate_match_explanation
from backend.services.skill_gap import analyze_skill_gap

logger = logging.getLogger(__name__)

# The re-ranker reports fit on 0-1; MatchResult.match_score is documented as a
# 0-100 score. Converted once, here, so the agent explains the same number the
# UI shows.
FIT_SCORE_SCALE = 100.0

# Free-text profile fields, in the order they are fed to the embedder. The CV
# parser and the UI form use different names for the same thing, so both spellings
# are accepted rather than forcing one lane to rename its fields.
PROFILE_TEXT_FIELDS = (
    "title",
    "current_title",
    "target_role",       # backend.models.profile.Profile
    "summary",
    "experience",
    "experience_level",  # backend.models.profile.Profile
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


def build_profile(profile: Any) -> Profile:
    """Adapt the UI's profile dict to the skill-gap lane's `Profile`.

    The CV parser produces `title`; `Profile` calls it `target_role`. Rather
    than make either lane rename its field, the mapping lives here, in the
    integration layer that already knows about both.
    """
    if not isinstance(profile, dict):
        profile = (
            profile.model_dump()
            if hasattr(profile, "model_dump")
            else dict(profile)
        )

    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",") if part.strip()]

    return Profile(
        user_id=str(profile.get("user_id") or "default"),
        skills=[str(s) for s in skills],
        target_role=(
            profile.get("target_role")
            or profile.get("title")
            or profile.get("current_title")
        ),
        experience_level=profile.get("experience_level"),
    )


def explain_ranked_job(
    entry: Dict[str, Any],
    profile: Profile,
    session: Any,
) -> Optional[Dict[str, Any]]:
    """Build a `MatchExplanation` dict for one ranked entry, or None.

    Returns None when the posting is not in SQLite, which happens if Qdrant and
    the database have drifted apart. Explaining a job we cannot look up would
    mean inventing its requirements, so it is skipped instead and the caller
    falls back to a placeholder.

    The score is never recomputed: `fit_score` from the re-ranker is passed
    through, and the agent explains that number as given.
    """
    job_id = entry.get("job_id")
    row = session.get(JobPostingORM, job_id) if job_id else None
    if row is None:
        logger.warning(
            "Ranked job %s is not in SQLite; skipping explanation", job_id
        )
        return None

    posting = orm_to_job_posting(row)

    # The Qdrant payload carries identity fields only, but the plan's rendered
    # match shows location, description and required skills too. The full
    # posting is already in hand from this join, so enrich the entry rather than
    # making the UI fetch it again at display time.
    job_data = entry.setdefault("job_data", {})
    job_data.setdefault("location", posting.location)
    job_data["description"] = posting.description
    job_data["required_skills"] = list(posting.skills)
    job_data["date_posted"] = (
        posting.date.date().isoformat() if posting.date else None
    )
    if posting.salary:
        job_data["salary"] = posting.salary

    gap = analyze_skill_gap(profile, required_skills_override=posting.skills)

    match_result = MatchResult(
        match_score=float(entry.get("fit_score") or 0.0) * FIT_SCORE_SCALE,
        matched_skills=list(gap.matched_skills),
        missing_skills=[item.skill for item in gap.gaps],
    )

    explanation = generate_match_explanation(
        profile=profile,
        job=JobInfo.from_job_posting(posting),
        match_result=match_result,
    )
    return explanation.model_dump()


def attach_explanations(
    ranked: List[Dict[str, Any]],
    profile: Any,
    session: Any,
) -> List[Dict[str, Any]]:
    """Add an `explanation` to each ranked entry, in place.

    One job failing to explain must not lose the whole result set, so each is
    guarded separately. The agent already degrades to a deterministic
    data-only explanation when Gemini is unavailable, so reaching this except
    means something unexpected rather than a flaky LLM.
    """
    profile_obj = build_profile(profile)
    for entry in ranked:
        try:
            explanation = explain_ranked_job(entry, profile_obj, session)
        except Exception:
            logger.exception(
                "Explanation failed for job %s", entry.get("job_id")
            )
            explanation = None
        if explanation is not None:
            entry["explanation"] = explanation
    return ranked


def run_match_pipeline(
    profile: Any,
    top_k: int = 10,
    llm_client: Optional[Any] = None,
    session: Any = None,
) -> List[Dict[str, Any]]:
    """Retrieve candidates for `profile`, re-rank them, return the ranking.

    `top_k` is the retrieval width, not the output size — the re-ranker
    narrows to its own top 3. Widening it gives the LLM more to choose from at
    the cost of a longer prompt.

    `llm_client` is injectable so tests can run the whole pipeline without a
    network call.

    `session` is the SQLAlchemy session used to join postings back for the
    explanation stage. Without one, explanations are skipped and the ranking is
    returned as-is, so the retrieval/ranking path stays usable on its own.

    Returns the re-ranker's `top_3` list: dicts of
    `{job_id, rank, fit_score, job_data}`, each with an `explanation` when the
    posting could be looked up. Empty when the profile has no usable text or
    retrieval finds nothing.
    """
    cv_text = profile_to_text(profile)
    if not cv_text.strip():
        return []

    jobs = retrieve_top_jobs(cv_text=cv_text, top_k=top_k)
    if not jobs:
        return []

    ranked = rerank_jobs(profile, jobs, client=llm_client).get("top_3", [])
    if ranked and session is not None:
        ranked = attach_explanations(ranked, profile, session)
    return ranked
