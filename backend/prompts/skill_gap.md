# Skill Gap - LLM-assisted pass (future sprint)

## Purpose

The Sprint 1 skill-gap analyzer (`backend/services/skill_gap.py`) is a
deterministic, frequency-based baseline. This prompt is a placeholder
for a **future** enhancement: catching skill synonyms/near-equivalents
that the static taxonomy (`backend/services/skill_taxonomy.py`) does
not yet know about, and producing a more nuanced natural-language
reason per gap (PRD Section 7.5 - Match Explanation).

This prompt is NOT wired up to any service yet. It is documented now,
per this repo's Prompt Policy (CONTRIBUTING.md), so the design is
reviewable before it is implemented.

## Used by (planned)

`backend/services/skill_gap.py` (an optional second pass, after the
deterministic baseline, not a replacement for it).

## Expected output format

Strict JSON, no prose outside the JSON object:

```json
{
  "additional_gaps": [
    {"skill": "<canonical skill name>", "reason": "<short explanation>"}
  ],
  "synonym_corrections": [
    {"raw": "<skill as seen in input>", "canonical": "<canonical name>"}
  ]
}
```

## Rules

- Do not invent skills, experience, dates, companies, or achievements
  that are not present in the supplied profile or job data.
- Only report a skill as missing if it is not present in the user's
  skill list (including synonyms) - never assume based on job title or
  role alone.
- If uncertain whether two skills are truly equivalent, do NOT merge
  them; leave them as separate entries so a human can review.
- Keep `reason` under 25 words, and always reference the specific
  skill and role by name (Responsible AI - Transparency, PRD Section 9).
