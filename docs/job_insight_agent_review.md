# Job Insight Agent — Production-Level Review (Pass 2)

**Scope:** `backend/routes/job_insight.py`, `backend/services/job_insight_agent.py`,
`backend/models/job_insight.py`, `backend/tests/test_job_insight_agent.py`

**Outcome:** Four small, behavior-preserving improvements applied to
`generate_job_insight` in `job_insight_agent.py`, plus one new test. No
architecture change, no API contract change, no business-logic change
(verified: all 52 pre-existing tests pass unmodified, with identical
`call_gemini` call counts for every scenario). Everything else reviewed
below was already production-ready and was left untouched.

---

## Findings and fixes

### 1 & 2. Duplicated code / hardcoded retry count — fixed

`generate_job_insight` previously called `call_gemini(...)` twice with five
identical kwargs, and the "one retry" behavior was only implicit in that
duplication — no constant defined it, unlike `_INSIGHT_TEMPERATURE` /
`_INSIGHT_RESPONSE_MIME_TYPE`, which already were centralized.

**Fix:**
- Extracted `_call_gemini_for_insight(prompt, model, api_key)` so the
  pinned generation config is written once.
- Added `_INSIGHT_MAX_ATTEMPTS = 2` and rewrote the body as
  `for attempt in range(1, _INSIGHT_MAX_ATTEMPTS + 1): ...`, mirroring the
  identical `max_attempts = 2` loop convention `gemini_client.call_gemini`
  already uses for its own transient-error retry — so this now follows an
  established, existing pattern rather than introducing a new one.
- Verified the subtle existing behavior is preserved: a `None` response
  (Gemini unavailable/unconfigured) still returns immediately without
  consuming a retry, since `call_gemini` already exhausts its own retry
  for transient errors and a `None` here means a non-transient condition.
  This is covered by `test_falls_back_when_gemini_unavailable`
  (`call_count == 1`), which still passes.

### 3. Logging consistency — fixed

The old code logged `invalid_json` on the first failure and
`invalid_json_after_retry` on the second — arbitrary message drift, and
inaccurate: `_try_parse_insight` returns `None` for both invalid JSON *and*
a schema-valid-but-incomplete response, yet the message always said
`invalid_json` regardless of which actually happened.

**Fix:** One consistent template per outcome, parametrized with
`attempt`/`_INSIGHT_MAX_ATTEMPTS`/`action` (`retry` or `fallback`):
`job_insight: invalid_or_incomplete_response job_id=%s attempt=%d/%d action=%s`.
Same for the "unavailable" case. Success and fallback-construction paths
were already fine and are unchanged.

### 4. Exception handling — a real gap, fixed

`_build_insight_prompt` → `_load_insight_prompt` reads `job_insight.md`
from disk with no error handling. If that file were ever missing or
unreadable in production, it would raise all the way up through the route
as an unhandled 500 — contradicting the module's own documented "this
NEVER raises for AI-related reasons" contract, which simply didn't cover
infra/config failures.

**Fix:** Wrapped the prompt-build call in `try/except Exception`, logging
`job_insight: prompt_build_failed job_id=%s action=fallback` via
`logger.exception` and degrading to `_fallback_insight` — consistent with
every other failure mode in this function. Deliberately scoped narrowly:
only the prompt-build step is guarded, not the whole function body, so a
genuine caller-contract violation (e.g. a malformed `matched_job` missing
`.job.job_id`) still fails loudly rather than being silently masked as a
fallback.

**New test:** `test_falls_back_gracefully_when_prompt_building_fails` —
patches `_build_insight_prompt` to raise `OSError`, asserts the function
returns the deterministic fallback and never calls Gemini.

---

## Re-verified, unchanged

### 5. Type hints & docstrings ✅
The new `_call_gemini_for_insight` helper and the updated
`generate_job_insight` docstring follow the same Google-style convention as
the rest of the file. Everything else was already complete (`pyflakes`
clean on all four files, before and after).

### 6. Naming consistency ✅
Prompt file (`job_insight.md`), service module (`job_insight_agent.py`),
route prefix (`/job-insight`), model file (`job_insight.py`), and the new
`_INSIGHT_MAX_ATTEMPTS` constant (matching the existing `_INSIGHT_*` prefix
convention) are all consistent.

### 7. Batch processing doesn't duplicate single-job logic ✅
Unchanged by this pass: `generate_top_matches_insights` still calls
`generate_job_insight` once per job via a plain list comprehension;
`generate_job_insights` and `generate_top_matches_summary` are both thin
compositions of `generate_top_matches_insights` + `build_ui_summary`. No
re-implementation anywhere.

---

## Verification performed

- `pyflakes` on all four files in scope — clean, before and after.
- `pytest backend/tests/test_job_insight_agent.py` — 52 pre-existing tests
  pass unmodified (same `call_gemini` call counts in every retry/fallback
  scenario) + 1 new test = 53 passed.
- Full repo test run — 247 passed, same 3 pre-existing failures in
  `test_match_explanation_agent.py` as before this pass (unrelated mock
  signatures in a different module, out of scope, not touched).

## Out-of-scope note (carried over from the previous review)

`match_explanation_agent.py` has the same "call `call_gemini` twice with a
manual retry" pattern this pass just refactored away in
`job_insight_agent.py`. Worth the same treatment in a future pass, but it's
a different module/lane and wasn't touched here.
