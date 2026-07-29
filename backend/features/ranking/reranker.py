"""LLM re-ranking of retrieved job postings.

Stage 2 of the matching pipeline. The retriever (`backend/features/matching/
retriever.py`) does cheap vector similarity over the whole collection; this
module takes its shortlist and asks an LLM to re-rank it with reasoning the
embedding cannot capture (seniority fit, skill substitutability, and so on).

Moved here from `LLM-ranking/backend/LLM.py`, which sat outside the `backend`
package and so could not be imported as `backend.*`. Four defects were fixed
in the move:

1. The body read an undefined name `m_response` instead of the `menna_jobs`
   parameter — every call raised NameError, so this had never run.
2. The client was a bare `OpenAI()` built at import time with a hardcoded
   `model="gpt-5.5"`. That ignores the project's configured provider and would
   raise at import if no OpenAI key were set. It now goes through the LiteLLM
   gateway declared in `.env.example` (LiteLLM is OpenAI-wire-compatible, so
   the same SDK works) and is built lazily.
3. `json.loads(content)` ran once outside the try/except and again inside it,
   so malformed output raised the raw JSONDecodeError the except was meant to
   convert.
4. The prompt's example output was itself invalid JSON (unclosed `job_data`
   objects) and described fields the input does not have — `required_skills`,
   `salary_range`, `date_posted`. It now mirrors the retriever's actual
   payload, so the model echoes real data instead of inventing those keys.

The `{"top_3": [...]}` output shape is unchanged: that is the ranking lane's
contract and reshaping it is not this module's call.
"""

import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# The retriever returns these keys per job; the prompt below promises the model
# nothing beyond them. See `docs/vector-store.md` for where they come from.
RETRIEVED_JOB_KEYS = (
    "job_id",
    "title",
    "company",
    "location",
    "url",
    "source",
    "match_score",
)

TOP_N = 3

_client: Optional[OpenAI] = None


class RerankError(RuntimeError):
    """The LLM returned something that is not usable as a ranking."""


def get_client() -> OpenAI:
    """Build the LiteLLM-backed client once, on first use.

    Lazy because constructing it reads credentials: doing that at import time
    would make `import backend.main` fail on any machine without the key set,
    which is exactly how the previous version broke.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.getenv("LITELLM_BASE_URL"),
            api_key=os.getenv("LITELLM_API_KEY"),
        )
    return _client


SYSTEM_PROMPT = """You are an expert job ranking assistant.

Your task:
- Analyse a list of job postings that were retrieved for a user.
- Re-rank them by how well they fit that user's profile.

Strict rules:
- Return ONLY valid JSON. No explanations, no markdown, no extra text.
- Return exactly the top 3 jobs, ranked 1 to 3.
- Copy each job's fields verbatim into job_data. Do not invent fields that
  were not given to you, and do not change any values.
- fit_score is your own 0.0-1.0 judgement of fit, not the match_score you
  were given.

Ranking criteria, in order of importance:
1. Relevance to the user's profile and stated goals
2. Skills match
3. Job title similarity
4. Experience level match

Output format:
{
  "top_3": [
    {
      "job_id": "a1b2c3d4",
      "rank": 1,
      "fit_score": 0.91,
      "job_data": {
        "job_id": "a1b2c3d4",
        "title": "Junior Data Analyst",
        "company": "Acme Corp",
        "location": "Cairo, Egypt",
        "url": "https://wuzzuf.net/jobs/p/a1b2c3d4",
        "source": "wuzzuf",
        "match_score": 0.78
      }
    }
  ]
}"""


def _strip_code_fence(content: str) -> str:
    """Drop a ```json ... ``` wrapper if the model added one anyway."""
    content = content.strip()
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()
    return content


def rerank_jobs(
    profile: Any,
    jobs: List[Dict[str, Any]],
    client: Optional[OpenAI] = None,
) -> Dict[str, Any]:
    """Re-rank `jobs` for `profile` and return `{"top_3": [...]}`.

    `jobs` is the retriever's output as-is — a flat list of dicts keyed by
    RETRIEVED_JOB_KEYS. `client` is injectable so tests never hit the network.

    Returns an empty ranking for empty input rather than paying for a call
    that has nothing to rank.
    """
    if not jobs:
        return {"top_3": []}

    jobs_json = json.dumps(jobs, ensure_ascii=False, default=str)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"User profile:\n{profile}\n\nJobs:\n{jobs_json}",
        },
    ]

    response = (client or get_client()).chat.completions.create(
        model=os.getenv("DEFAULT_MODEL", "FW-Kimi-K2.6"),
        messages=messages,
    )
    content = response.choices[0].message.content

    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise RerankError(f"LLM did not return valid JSON: {content!r}") from exc

    if not isinstance(data, dict) or "top_3" not in data:
        raise RerankError(f"LLM response is missing 'top_3': {data!r}")

    return data
