"""LLM re-ranking of retrieved job postings.

Stage 2 of the matching pipeline. The retriever (`backend/features/matching/
retriever.py`) does cheap vector similarity over the whole collection; this
module takes its shortlist and asks an LLM to re-rank it with reasoning the
embedding cannot capture (seniority fit, skill substitutability, and so on).

The ranking logic, the prompt, the Gemini provider and the `{"top_3": [...]}`
output contract are Ramez's, from `feature/llm-rerankingb` (PR #20), which is
the version the team chose. This module is that implementation moved into the
backend package.

Why it had to move: the original lives at `LLM-ranking/backend/LLM.py`, and
`LLM-ranking` contains a hyphen, so `LLM-ranking.backend.LLM` is not a valid
Python module path — nothing in `backend/` can ever import it from there. It
also did `from retriever import retrieve_top_jobs`, which only resolves when
that directory happens to be on `sys.path`, and shipped its own copy of the
retriever. Here it imports Menna's retriever through the package instead, so
there is one retriever rather than two that can drift.

Integration changes on top of Ramez's logic, all additive:
- the Gemini client is built lazily and can be injected, so tests never need a
  key or a network call;
- empty input short-circuits instead of paying for a call with nothing to rank;
- `job_data` is reconciled against the retrieved postings — see
  `_reconcile_job_data` for why that matters.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# The retriever returns exactly these keys per job. Ramez's prompt asks the
# model for a richer job_data (description, skills, salary_range,
# date_posted...) than the retriever actually supplies, so the model would have
# to invent the difference. `_reconcile_job_data` drops whatever it invents.
RETRIEVED_JOB_KEYS = (
    "job_id",
    "title",
    "company",
    "location",
    "url",
    "source",
    "match_score",
)

# PR #20 hardcoded "gemini-1.5-flash", which Google has since retired: new API
# keys get `404 ... is not found for API version v1beta` on generateContent.
# "gemini-flash-latest" is an alias that tracks the current flash model, so it
# does not rot the same way, and it is what backend/services/llm_service.py
# already uses successfully for CV parsing. Override with RANKING_MODEL.
DEFAULT_RANKING_MODEL = "gemini-flash-latest"


def ranking_model_override() -> Optional[str]:
    """RANKING_MODEL if set, else None meaning "use the provider's default".

    None rather than a hardcoded fallback, because the default differs per
    provider: the gateway serves DEFAULT_MODEL, Gemini serves GEMINI_MODEL.
    Returning a Gemini model id here would send it to the gateway, which does
    not serve it.
    """
    return os.getenv("RANKING_MODEL") or None


def ranking_model() -> str:
    """A concrete model id, for the direct-client path.

    Read at call time so .env changes apply without reimporting, and so tests
    can override it.
    """
    return ranking_model_override() or DEFAULT_RANKING_MODEL


class RerankError(RuntimeError):
    """The LLM returned something that is not usable as a ranking."""


def _build_contents(profile: Any, jobs_json: str) -> List[Dict[str, Any]]:
    """Ramez's prompt, verbatim apart from the interpolation points."""
    return [
        {
            "role": "user",
            "parts": [
                {
                    "text": f"""
You are an expert job ranking assistant.

Return ONLY a valid JSON response.

You MUST strictly follow this exact JSON structure:

{{
  "top_3": [
    {{
      "job_id": "string",
      "rank": number,
      "fit_score": number,
      "job_data": {{
        "job_id": "string",
        "title": "string",
        "company": "string",
        "location": "string",
        "source": "string",
        "url": "string"
      }}
    }}
  ]
}}

Rules:
- Return exactly 3 items in "top_3"
- Ranks MUST be: 1, 2, 3 (no duplicates)
- fit_score must be between 0 and 1
- Copy job_data fields verbatim from the job you were given; do not invent
  fields or change values
- Do NOT add any explanation
- Do NOT add text outside JSON

Ranking criteria (in order of importance):
1. Relevance to user cv
2. Required skills match
3. Job title similarity
4. Experience level match

---

User profile:
{profile}

Jobs:
{jobs_json}
"""
                }
            ],
        }
    ]


# Gemini returns 503 "experiencing high demand" under load. That is transient
# and retrying usually clears it, so it should not surface as a failed request.
TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "high demand", "429",
                     "RESOURCE_EXHAUSTED")
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0


def _is_transient(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in TRANSIENT_MARKERS)


def _prompt_text(contents: Any) -> str:
    """Flatten Ramez's Gemini `contents` structure back to a plain prompt.

    The shared client takes a prompt string, since it has to serve providers
    whose request shapes differ. The prompt itself is unchanged.
    """
    try:
        return contents[0]["parts"][0]["text"]
    except (IndexError, KeyError, TypeError):
        return str(contents)


def _generate_with_retry(client: Any, model: str, contents: Any):
    """Call the model, retrying transient overload errors with backoff.

    A retired or misspelled model gives a 404, which is a config problem and is
    surfaced immediately with a pointer at RANKING_MODEL rather than retried.
    Overload (503 / 429) is retried, because failing the user's request over a
    momentary capacity spike is the wrong trade.
    """
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config={"response_mime_type": "application/json"},
            )
        except Exception as exc:
            if "404" in str(exc) or "NOT_FOUND" in str(exc):
                raise RerankError(
                    f"Ranking model {model!r} is unavailable for this API key "
                    f"(404 from Gemini). Set RANKING_MODEL in .env to a model "
                    f"your key can use. Original error: {exc}"
                ) from exc
            if not _is_transient(exc):
                raise
            last_exc = exc
            logger.warning(
                "Ranking model %s returned a transient error (attempt %d/%d): %s",
                model, attempt + 1, RETRY_ATTEMPTS, exc,
            )
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))

    raise RerankError(
        f"Ranking model {model!r} was overloaded after {RETRY_ATTEMPTS} "
        f"attempts. This is usually temporary; try again shortly. "
        f"Last error: {last_exc}"
    ) from last_exc


def _reconcile_job_data(
    entry: Dict[str, Any], jobs_by_id: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Replace the model's `job_data` with the real retrieved posting.

    The LLM is asked to echo job data back, and LLMs paraphrase, drop and
    invent fields when they do that. Since the true posting is already in hand,
    the model's copy is thrown away and the retrieved one substituted, joined on
    `job_id`. The model's genuine contributions — `rank` and `fit_score` — are
    kept.

    An entry whose `job_id` was never retrieved is dropped: the model made it
    up, and a fabricated job must not reach the UI.
    """
    job_id = entry.get("job_id") or (entry.get("job_data") or {}).get("job_id")
    real = jobs_by_id.get(job_id)
    if real is None:
        return {}
    return {
        "job_id": job_id,
        "rank": entry.get("rank"),
        "fit_score": entry.get("fit_score"),
        "job_data": real,
    }


def rerank_jobs(
    profile: Any,
    jobs: List[Dict[str, Any]],
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Re-rank `jobs` for `profile` and return `{"top_3": [...]}`.

    `jobs` is the retriever's output as-is — a flat list of dicts keyed by
    RETRIEVED_JOB_KEYS. `client` is injectable so tests never hit the network.
    """
    if not jobs:
        return {"top_3": []}

    jobs_json = json.dumps(jobs, ensure_ascii=False, default=str)
    contents = _build_contents(profile, jobs_json)

    model = ranking_model()
    if client is not None:
        # An injected client is a test double; use it directly.
        response = _generate_with_retry(client, model, contents)
        content = response.text
    else:
        # Otherwise go through the shared provider switch, so ranking uses the
        # same gateway as every other LLM call rather than its own Gemini key.
        from backend.services.llm_client import complete

        content = complete(
            _prompt_text(contents),
            model=ranking_model_override(),
            temperature=0.2,
            response_mime_type="application/json",
        )
        if content is None:
            raise RerankError(
                "The ranking model returned nothing. Check AI_PROVIDER, "
                "LITELLM_BASE_URL and LITELLM_API_KEY."
            )

    # Strip a ```json fence: models add one even when asked for raw JSON, and
    # the gateway's models are no more obedient about it than Gemini was.
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RerankError(
            f"LLM did not return valid JSON: {content!r}"
        ) from exc

    if not isinstance(data, dict) or "top_3" not in data:
        raise RerankError(f"LLM response is missing 'top_3': {data!r}")

    jobs_by_id = {job.get("job_id"): job for job in jobs}
    reconciled = [_reconcile_job_data(e, jobs_by_id) for e in data["top_3"]]
    return {"top_3": [entry for entry in reconciled if entry]}


# Ramez's lane calls this `create_llm`; keep the name working so his callers
# do not have to change.
create_llm = rerank_jobs
