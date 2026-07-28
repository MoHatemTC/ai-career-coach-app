# Match Explanation Agent - explanation prompt

## Purpose

The Skill Gap Analyzer (`backend/services/skill_gap.py`) and the
matching engine already produce a deterministic, final result: a
`match_score`, a list of `matched_skills`, and a list of
`missing_skills`. This prompt does NOT recompute any of that. It asks
Gemini to explain, in plain language, what that already-final result
means for the candidate - strengths, gaps, and next steps - without
touching the numbers or skill lists themselves.

This keeps the same separation this repo already uses for semantic
skill matching (`backend/prompts/skill_gap.md`): deterministic
calculation stays in Python; the LLM only classifies/explains,
never scores (PRD Section 9 - Transparency).

## Critical instructions

- Never calculate a score.
- Never modify a score.
- Never invent skills.
- Never invent requirements.
- Never contradict the deterministic analyzer (the match_score,
  matched_skills, and missing_skills you are given).
- Answer/explain only using the supplied context - do not bring in
  outside assumptions about the candidate, the job, or the company.
- Return valid JSON only.

## Used by

`backend/services/match_explanation_agent.py`
(`generate_match_explanation`). Called once per candidate/job pair;
the result is cached in an `AgentContext`
(`backend/models/agent_context.py`) and never regenerated for the same
pair - see that module's docstring.

## Expected output format

Strict JSON, no prose outside the JSON object, no Markdown code
fences:

```json
{
  "overall_alignment_summary": "<2-4 sentence summary of overall fit>",
  "strengths": [
    "<short bullet, referencing only skills from matched_skills>"
  ],
  "gaps_or_missing_requirements": [
    "<short bullet, referencing only skills from missing_skills>"
  ],
  "recommendations": [
    "<short, actionable bullet the candidate could act on>"
  ],
  "next_steps": [
    "<short, concrete next action, e.g. 'Apply, highlighting X'>"
  ]
}
```

This exact shape is validated against a Pydantic schema
(`backend.services.match_explanation_agent.MatchExplanation`) before
it is used or stored in an `AgentContext`.

## Rules

- You are given a `match_score` that has ALREADY been calculated by a
  separate deterministic matching engine. Do NOT calculate, restate as
  a different number, adjust, or second-guess this score in any way.
  Your explanation must be consistent with it - if the score is high,
  do not describe the candidate as a poor fit, and vice versa.
- You are given `matched_skills` and `missing_skills` lists that have
  ALREADY been determined. Do NOT invent skills, requirements,
  experience, dates, companies, or achievements that are not present
  in the candidate profile, job information, or these two lists.
- Every item in `strengths` must reference only skills that appear in
  `matched_skills`. Every item in `gaps_or_missing_requirements` must
  reference only skills that appear in `missing_skills`. Do not
  introduce a skill in either list that isn't already there.
- `recommendations` and `next_steps` may offer general career advice
  (e.g. "highlight X in your CV", "consider a short course in Y") but
  must stay grounded in the provided missing/matched skills - do not
  invent new required skills to recommend against.
- Return ONLY the JSON object - no preamble, no trailing commentary,
  no Markdown code fences. The entire response must be valid,
  parseable JSON matching the schema above.
