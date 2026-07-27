# Streamlit UI Framework

A standalone Streamlit app for the career-coach flow: upload a CV, review the
parsed profile, and see job matches. It talks to the FastAPI backend over HTTP
and runs as its own process.

**Everything runs locally.** The backend is `localhost:8000`, its database is
the local SQLite file, and Qdrant (when used) is the local docker-compose
service. No hosted services, no API keys.

## What is real vs mocked

This matters more than anything else in this doc — the UI is deliberately
clickable end-to-end *today*, with one clearly-marked seam where the real
matching chain will land.

| Part of the flow | Status | Where |
| --- | --- | --- |
| CV upload + parsing | **REAL** — hits the backend `/upload`, which runs the actual parser | `api_client.upload_cv` |
| Editable profile form | **REAL** — your edits are what get passed on | `chatbot_ui.py` |
| Job matching + explanations | **MOCKED** — hardcoded results | `pipeline_stub.run_matching_pipeline` |
| Notification settings | **REAL** — persisted to SQLite | `api_client` → `/notifications/*` |

The mock is visibly flagged in the UI itself (a banner above the results), so
nobody demoing it mistakes the match cards for real output.

## Files

```
streamlit_app/
├── chatbot_ui.py       # main entry: "Career Chat" and "Settings" tabs
├── api_client.py       # thin HTTP wrappers around the backend
└── pipeline_stub.py    # THE MOCK BOUNDARY — replace this one function
```

Split this way so the seam is a single function rather than something tangled
through the UI.

### `pipeline_stub.py` — the one function to replace

```python
run_matching_pipeline(profile: dict) -> list[dict]
```

Currently returns 3 hardcoded results. When the real chain is ready, replace
the *internals* only:

1. **Menna** — embed the profile, search the Qdrant `job_postings` collection
   (see `docs/vector-store.md`) → candidate jobs
2. **Ramez** — rank those candidates against the profile
3. **Farag** — generate a `MatchExplanation` per ranked job

**The return shape is the contract.** Each dict must have the keys in
`MATCH_RESULT_KEYS`: `job_title`, `company`, `strength`, `weakness`,
`recommendation` — shaped like Farag's `MatchExplanation`. The UI renders
exactly these in `render_match_card`; change one and you must change the other.
The UI shows a warning if a result is missing an expected key, so a shape
mismatch surfaces immediately instead of rendering blanks.

## Running it

Two processes, two terminals. Backend first:

```bash
uvicorn backend.main:app --reload            # terminal 1 — localhost:8000
streamlit run streamlit_app/chatbot_ui.py    # terminal 2 — localhost:8501
```

The UI shows a red banner if it cannot reach the backend, so a missing
terminal 1 is obvious rather than mysterious.

Backend location comes from `.env` (`BACKEND_HOST` / `BACKEND_PORT`,
defaulting to `127.0.0.1:8000`). A `0.0.0.0` host is mapped to loopback for
outbound calls, since it is a bind address rather than a connectable one.

## Career Chat tab

1. **Upload** a PDF/DOCX → `POST /upload` → the parsed profile comes back.
2. **Review** it in an editable form — text inputs for name/email/phone/title,
   a multiselect for skills (you can remove wrong ones and type new ones), and
   text areas for experience/education. The parser is a starting point, not the
   final word, so this step exists to correct it.
3. **Confirm** → calls `run_matching_pipeline(profile)` → renders each result
   as a card with strength / weakness / recommendation.

Editing the profile clears any previous results, so what is on screen always
corresponds to the profile that produced it.

## Settings tab

Email and phone, saved via `POST /notifications/settings`.

Stored in the `notification_settings` SQLite table rather than a module-level
variable, because an in-memory value is lost on every backend restart — a real
risk mid-demo. The notifications lane can read the values independently:

```
GET /notifications/settings/{user_id}
```

Returns 404 if nothing has been saved for that user yet. There is no auth in
the UI, so everything is stored under `user_id="default"`; the id is threaded
through the API as a parameter, so adding real users later is a UI change
rather than a schema change.
