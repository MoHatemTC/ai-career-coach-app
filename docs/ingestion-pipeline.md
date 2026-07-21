# Ingestion Pipeline

How ingested job postings are normalized, deduplicated, persisted, and
triggered/monitored. This covers the persistence layer added on top of the
existing ingestion clients (`backend/services/ingestion.py`).

## Overview

```
sources (Arbeitnow / Wuzzuf / Mock-MENA)
        │  get_jobs(limit) -> List[JobPosting]
        ▼
run_ingestion()  ──►  upsert by job_id  ──►  job_postings table
        │                                     (SQLite via SQLAlchemy)
        └──────────────►  ingestion_runs table (status + counts)
                                    ▲
                                    │  polled over HTTP
                          FastAPI routes  ◄──►  Streamlit dashboard
```

## Normalization schema

Every source is normalized into the canonical `JobPosting` Pydantic model
(`backend/models/job.py`) — the single shared contract imported by other lanes
(matching, skill-gap). Fields:

| Field | Notes |
| --- | --- |
| `job_id` | deterministic `sha256(url)[:16]` (see dedup below) |
| `title`, `company` | required, validated non-blank |
| `location`, `description`, `url` | `url` must start with `http` |
| `skills` | **real skills only** |
| `job_type` | e.g. "Full Time", "Part Time" |
| `work_mode` | e.g. "On-site", "Remote", "Hybrid" |
| `career_level` | e.g. "Manager", "Experienced", "Entry" |
| `experience_years` | raw range string, e.g. "5 - 10 Yrs of Exp" |
| `salary`, `source`, `date` | |

### Why metadata chips are split out of `skills`

Wuzzuf renders job-type, work-mode, seniority, and experience-range chips in
the *same* markup block as real skills. If left mixed in, the skill-gap lane —
which treats any unmatched string as a legitimate "unknown skill" — would count
tokens like `"Full Time"`, `"On-site"`, or `"5 - 10 Yrs of Exp"` as fake
skills, polluting its frequency signal. `classify_wuzzuf_tag()` buckets each
chip mechanically (exact-match sets + one regex for experience ranges) so only
genuine skills land in `skills`; the metadata populates the dedicated fields,
where the matching lane can actually use it.

> Known debt: Arbeitnow returns only a single broad category tag (e.g.
> `["Engineering"]`) rather than granular skills — tracked for a later pass.

## Deduplication & resolution

- **Detection key:** `job_id`, the deterministic `sha256` of the posting URL.
- **Resolution:** upsert. For each ingested posting, look it up by `job_id`;
  insert if absent (`jobs_inserted`), otherwise overwrite the stored row with
  the freshly ingested values (`jobs_updated`). Invalid postings (fail Pydantic
  validation) are counted `jobs_skipped` and never persisted.

### Why URL-hash as the key

The public sources expose no stable, uniform id, but a posting's URL is stable
and unique per posting. Hashing it gives a deterministic key that is identical
across runs *and* across clients, without depending on any source-specific id
scheme — so re-scraping the same posting always targets the same row, which is
exactly what makes upsert (rather than blind insert) possible.

### Why overwrite on conflict

Each run is treated as the source of truth: a re-scrape may carry a corrected
description (e.g. the Wuzzuf description fix) or an updated posting date, so the
newer values win rather than being discarded as a "duplicate".

## Database schema

SQLAlchemy ORM (`backend/models/db_models.py`), created on app startup via
`init_db()` (`backend/services/database.py`).

### `job_postings`

Mirrors `JobPosting` exactly, with `job_id` as the **primary key** (so upsert is
a direct PK lookup) and `skills` stored as a **JSON-encoded string** (SQLite has
no native array type; `job_posting_to_orm` / `orm_to_job_posting` handle the
conversion). Adds `created_at` / `updated_at` timestamps.

### `ingestion_runs`

One row per run — what the dashboard polls to monitor progress:

`id`, `started_at`, `finished_at`, `source` (requested set, comma-joined),
`jobs_fetched`, `jobs_inserted`, `jobs_updated`, `jobs_skipped`,
`status`, `error_message`.

`status` values:

- `running` — in progress.
- `success` — every requested source completed.
- `partial` — at least one source succeeded and at least one failed
  (per-source detail in `error_message`).
- `failed` — every source failed, or a catastrophic error occurred.

Each source's fetch+upsert runs in its own transaction, so a mid-run failure on
one source never leaves a half-written batch and never discards another
source's already-persisted jobs.

### Why SQLite now, Postgres later

SQLite is file-based and zero-setup — enough for internal ingestion volumes and
lets the whole team run the pipeline with no database server. The persistence
layer is plain SQLAlchemy and reads `DATABASE_URL` from the environment, so
moving to PostgreSQL later is a `DATABASE_URL` change, not a code change. (No
Alembic yet — `create_all` on startup is sufficient for this stage.)

## Running the pipeline

### Via the API

```bash
uvicorn backend.main:app --reload        # http://localhost:8000, Swagger at /docs
```

- `POST /ingestion/run` — body `{"sources": ["mock_mena"], "limit": 5}`
  (both optional; sources default to all). Returns `{"run_id": N}` immediately;
  the run executes in the background.
- `GET /ingestion/runs/{run_id}` — that run's live status and counts.
- `GET /ingestion/runs` — recent runs, newest first.
- `GET /ingestion/jobs?limit=50&offset=0` — persisted postings, paginated.

The SQLite file (`career_coach.db` by default) is created automatically and is
git-ignored.

### Via the Streamlit dashboard

A separate process that talks to the backend over HTTP. Start the backend
first, then:

```bash
streamlit run streamlit_app/ingestion_dashboard.py   # http://localhost:8501
```

Pick sources and a limit, click **Run Ingestion**, and watch the run poll to
completion; the **Recent Runs** and **Persisted Jobs** tables read from the
same API. The backend URL comes from `BACKEND_HOST` / `BACKEND_PORT` in `.env`
(defaults to `127.0.0.1:8000`).

## Tests

`backend/tests/test_ingestion_pipeline.py` covers the upsert logic against an
in-memory SQLite DB: same `job_id` updates in place rather than duplicating, and
an invalid posting is counted `jobs_skipped` without crashing the run.

```bash
pytest backend/tests/ -q
```
