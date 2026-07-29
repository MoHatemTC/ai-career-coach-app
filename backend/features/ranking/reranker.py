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
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

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

MODEL_NAME = os.getenv("RANKING_MODEL", "gemini-1.5-flash")

_client = None


class RerankError(RuntimeError):
    """The LLM returned something that is not usable as a ranking."""


def get_client():
    """Build the Gemini client once, on first use.

    Lazy because constructing it reads credentials: doing that at import time
    makes `import backend.main` fail on any machine without the key set.
    """
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client()
    return _client


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

    response = (client or get_client()).models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config={"response_mime_type": "application/json"},
    )

    try:
        data = json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RerankError(
            f"LLM did not return valid JSON: {response.text!r}"
        ) from exc

    if not isinstance(data, dict) or "top_3" not in data:
        raise RerankError(f"LLM response is missing 'top_3': {data!r}")

    jobs_by_id = {job.get("job_id"): job for job in jobs}
    reconciled = [_reconcile_job_data(e, jobs_by_id) for e in data["top_3"]]
    return {"top_3": [entry for entry in reconciled if entry]}


# Ramez's lane calls this `create_llm`; keep the name working so his callers
# do not have to change.
create_llm = rerank_jobs
