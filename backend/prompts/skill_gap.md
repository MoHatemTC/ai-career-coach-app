# Skill Gap - Gemini semantic-matching pass

## Purpose

The Sprint 1 skill-gap analyzer (`backend/services/skill_gap.py`) is a
deterministic, taxonomy/frequency-based baseline (exact + alias
matching via `backend/services/skill_taxonomy.py`). That baseline
cannot catch *semantic* equivalents it has no alias entry for yet -
e.g. "FastAPI" satisfying a "REST API Development" requirement, or
"PyTorch" satisfying "Deep Learning".

This prompt drives a second, optional pass that asks Gemini to find
those semantic equivalents. It runs ONLY on the skills the
deterministic baseline could not already match, and it is strictly a
*classifier*, not a decision-maker: it does not compute match scores,
priorities, or recommendations. All of that stays in Python
(`backend/services/skill_gap.py`), per the Responsible-AI transparency
requirement (PRD Section 9) that every gap must be explainable and
reproducible, not the output of an opaque model call.

## Used by

`backend/services/gemini_matcher.py`, called from
`backend/services/skill_gap.py` as an optional augmentation step
*after* the deterministic taxonomy baseline runs - never a replacement
for it, and never on the critical path when `GEMINI_API_KEY` is unset
or the call fails (see that module's fallback behavior).

## Expected output format

Strict JSON, no prose outside the JSON object, no Markdown code
fences:

```json
{
  "matched_skills": [
    {
      "required_skill": "<canonical required skill, verbatim from input>",
      "candidate_skill": "<canonical candidate skill, verbatim from input>",
      "confidence": 0.97,
      "reason": "<short explanation, under 25 words>"
    }
  ],
  "partially_matched": [
    {
      "required_skill": "<canonical required skill, verbatim from input>",
      "candidate_skill": "<canonical candidate skill, verbatim from input>",
      "confidence": 0.76,
      "reason": "<short explanation, under 25 words>"
    }
  ],
  "missing_skills": [
    {
      "required_skill": "<canonical required skill, verbatim from input>",
      "reason": "<short explanation, under 25 words>"
    }
  ]
}
```

This exact shape is validated against a Pydantic schema
(`backend.services.gemini_matcher.SemanticMatchResult`) before any of
it is used. Every required skill passed in must appear in exactly one
of the three lists.

## Rules

- Only compare the candidate's skills against the required skills
  given to you. Do not invent, assume, or infer skills, experience,
  dates, companies, or achievements that are not present in the
  supplied lists.
- Do NOT calculate a match score, priority, or ranking. Do NOT produce
  recommendations. That is out of scope for this prompt - return only
  the classification above.
- "matched_skills" = the candidate skill is a genuine semantic
  equivalent of the required skill (e.g. "GitHub" / "Git", "TensorFlow"
  / "Deep Learning").
- "partially_matched" = related but not equivalent - the candidate
  skill provides some, but not full, coverage of the requirement.
- "missing_skills" = no candidate skill provides meaningful coverage.
- If uncertain whether two skills are truly equivalent, classify as
  "partially_matched" rather than "matched_skills" so a human can
  review it.
- Keep `reason` under 25 words, and always reference the specific
  skill names involved (Responsible AI - Transparency, PRD Section 9).
- Return ONLY the JSON object - no preamble, no trailing commentary,
  no Markdown code fences.

### Output integrity rules

- Every required skill given to you must appear EXACTLY ONCE across
  the three lists combined - never omitted, never duplicated.
- A given required skill must never appear in more than one list. It
  cannot be both "matched_skills" and "partially_matched", for
  example - pick the single best-fitting category.
- `confidence` must be a number between 0.0 and 1.0 inclusive. Never
  omit it, and never use a value outside that range.
- Do not invent skills that are not present in the candidate or
  required-skills lists you were given.
- Return valid JSON only - the entire response must be a single JSON
  object matching the schema above, parseable as-is.
