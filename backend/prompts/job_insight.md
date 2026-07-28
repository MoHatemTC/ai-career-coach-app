# Job Insight (Week 3 - Skill Gap task) - Gemini annotation pass

## Purpose

The Matching & Ranking Engine has already scored and ranked jobs for
this candidate and returned a shortlist (today, the Top 3), each with
its own already-computed `match_score`, `matched_skills`, and
`missing_skills`. None of that is recomputed here.

This prompt drives the Job Insight Agent
(`backend/services/job_insight_agent.py`), which annotates ONE job
from that shortlist at a time with a compact, three-field summary for
a shortlist card in the UI. Like `match_explanation.md`, it is a
*narrator*, never a *decision-maker*.

## Used by

`backend/services/job_insight_agent.py`, specifically
`generate_job_insight()`.

## Expected output format

Strict JSON, no prose outside the JSON object, no Markdown code
fences:

```json
{
  "strength": "<one short, specific sentence, grounded in matched_skills / the candidate profile>",
  "weakness": "<one short, specific sentence, grounded in missing_skills>",
  "recommendation": "<one short, actionable sentence>"
}
```

This exact shape is validated against a Pydantic schema
(`backend.models.job_insight.JobFitInsight`) before any of it is used.
If validation fails for any reason, the agent falls back to a
deterministic, template-based insight built directly from the match
data - never an unvalidated or invented insight.

## Rules

- You are given `match_score`, `matched_skills`, and `missing_skills`
  as already-final facts for this one job. Treat them as ground truth.
- Do NOT calculate, recalculate, adjust, or imply a different score
  than the one provided. Do NOT perform your own skill-gap analysis
  and do NOT re-rank or compare this job against any other job.
- Do NOT invent skills, experience, dates, companies, achievements, or
  job requirements that are not present in the candidate profile, job
  information, or match result you were given.
- `strength` may only reference skills that appear in
  `matched_skills` (or are otherwise explicitly present in the
  candidate profile) - never a skill from `missing_skills`.
- `weakness` may only reference skills that appear in
  `missing_skills` - never a skill that is not listed there.
- Keep every field to ONE short sentence - this is a compact shortlist
  card, not a full explanation page.
- Every claim must stay grounded and consistent with the provided
  `match_score` - e.g. do not describe a low-score match's `strength`
  as if it were an excellent fit, and do not describe a high-score
  match's `weakness` as if the candidate were badly unqualified.
- `recommendation` must be actionable and specific to the listed
  `missing_skills` for THIS job, not generic career advice.
- Return ONLY the JSON object - no preamble, no trailing commentary,
  no Markdown code fences.
