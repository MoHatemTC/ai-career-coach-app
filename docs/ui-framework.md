# Streamlit UI Framework

A standalone Streamlit app for the career-coach flow: upload a CV, review the
parsed profile, and see job matches. It talks to the FastAPI backend over HTTP
and runs as its own process.

**Everything runs locally.** The backend is `localhost:8000`, its database is
the local SQLite file, and Qdrant (when used) is the local docker-compose
service. No hosted services, no API keys.

## What is real vs mocked

Every stage is wired to a real service. The two fallbacks below exist only for
degraded backends, and both announce themselves in the UI when they trigger.

| Part of the flow | Status | Where |
| --- | --- | --- |
| CV upload + parsing | **REAL** — hits the backend `/upload`, which runs the actual parser | `api_client.upload_cv` |
| Editable profile form | **REAL** — your edits are what get passed on | `chatbot_ui.py` |
| Job retrieval | **REAL** — Qdrant vector search | `POST /matching/pipeline` → `retrieve_top_jobs` |
| Job ranking | **REAL** — LLM re-ranker via Gemini | `POST /matching/pipeline` → `rerank_jobs` |
| Written explanations | **REAL** — Match Explanation Agent | `POST /matching/pipeline` → `attach_explanations` |
| Chat intent routing | **REAL** — conversational agent | `POST /chat` → `chatbot_ui._route_message` |
| Notification settings | **REAL** — persisted to SQLite | `api_client` → `/notifications/*` |

**Fallback 1: `_route_by_keyword`.** Used when `POST /chat` returns 404, i.e.
the conversational-agent lane is not deployed on that backend. The chat then
handles "find matches" by keyword and says so, rather than appearing broken.

**Fallback 2: `placeholder_explanation`.** Used when a ranked job is missing
from SQLite, which means Qdrant and the database have drifted apart. It returns
**empty** `strengths`, `gaps_or_missing_requirements`, `recommendations` and
`next_steps` and reports only the figures the pipeline genuinely produced. An
earlier version returned fully-written fake analysis, which is worse than
returning nothing: it is indistinguishable from the real agent's output.

## Files

```
streamlit_app/
├── chatbot_ui.py       # main entry: "Career Chat" and "Settings" tabs
├── api_client.py       # thin HTTP wrappers around the backend
├── digest.py           # builds the notification digest (no Streamlit import)
└── pipeline_stub.py    # assembles pipeline output for rendering
```

`digest.py` deliberately imports no Streamlit: importing the UI script executes
it in bare mode, which dirties Streamlit's container context and breaks any
`AppTest` running afterwards. Anything that needs a unit test lives outside
`chatbot_ui.py` for that reason.

### Why the UI calls the pipeline over HTTP

`QDRANT_MODE=local` runs Qdrant embedded and takes an **exclusive lock** on its
storage directory. While the backend holds that lock, no other process can open
the collection — so a UI that imported the retriever and queried Qdrant
in-process would fail whenever the backend was running. The pipeline therefore
lives in `backend/services/matching_pipeline.py` and the UI calls
`POST /matching/pipeline`, like every other backend call it makes.

### The chain today

1. **Menna** — embed the profile, search the Qdrant `job_postings` collection
   (see `docs/vector-store.md`) → candidate jobs. **Wired.**
2. **Ramez** — LLM re-rank those candidates → `{"top_3": [...]}`. **Wired.**
3. **Farag** — generate a `MatchExplanation` per ranked job. **Wired.**
   `generate_match_explanation(profile, job, match_result)` needs a `JobInfo`
   with `required_skills` and a `MatchResult` with matched/missing skills, and
   the Qdrant payload carries neither. So `attach_explanations` joins the full
   posting back from SQLite on `job_id`, runs `analyze_skill_gap` against its
   skills, and passes the re-ranker's `fit_score` through unchanged. Nothing
   recomputes the score; the agent explains the number it is given.

**The return shape is the contract.** Each result pairs a job's identity with
its explanation:

```python
{
    "job_title": str,
    "company": str,
    "url": str | None,                      # link to the posting, from the payload
    "explanation": {                        # mirrors MatchExplanation exactly
        "overall_alignment_summary": str,
        "strengths": [str],
        "gaps_or_missing_requirements": [str],
        "recommendations": [str],
        "next_steps": [str],
    },
}
```

The nested `explanation` is field-for-field identical to the real
`MatchExplanation` model, so the real object drops in as
`explanation=match_explanation.model_dump()` with no other change.

Title and company sit **outside** `explanation` on purpose: the real
`MatchExplanation` carries no job identity at all — it only explains an
already-computed `MatchResult`. That identity comes from the retrieval step
instead (the Qdrant payload already carries `title` and `company`; see
`docs/vector-store.md`).

The UI renders exactly these in `render_match_card`; change one and you must
change the other. It warns when a result is missing a top-level key *or* an
explanation key, so a shape mismatch surfaces immediately instead of rendering
blanks. Empty list fields are skipped rather than printing bare headings, which
matches the real model's behaviour of defaulting every list to empty.

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

Contact details plus notification preferences, saved via
`POST /notifications/settings`. This tab is the producer of **Contract 6**, the
shape the notifications lane consumes:

```json
{
  "user_id": "default",
  "contact": { "email": "...", "phone_whatsapp": "+20..." },
  "notification_channels": ["email", "whatsapp"],
  "frequency": "daily",
  "relevance_threshold": 0.75
}
```

`contact` is nested per the contract; the table stores those fields flat since
that is what SQLite indexes, and the nesting is applied at the route boundary.
A contact-only save leaves the preferences untouched rather than blanking them,
and a brand-new row is given the contract's defaults so the notifications lane
never receives a half-populated object.

Channels are constrained to `email` and `whatsapp`. Note PRD 7.8 specifies email
only for v1; both are storable, and which are honoured is the sender's call.

Stored in the `notification_settings` SQLite table rather than a module-level
variable, because an in-memory value is lost on every backend restart — a real
risk mid-demo. The notifications lane reads the values independently:

```
GET /notifications/settings/{user_id}
```

Returns 404 if nothing has been saved for that user yet. There is no auth in
the UI, so everything is stored under `user_id="default"`; the id is threaded
through the API as a parameter, so adding real users later is a UI change
rather than a schema change.
