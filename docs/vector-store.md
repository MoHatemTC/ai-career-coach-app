# Vector Store — the Embedding Contract

Job postings are mirrored into a [Qdrant](https://qdrant.tech/) collection so
the matching lane can run similarity search (e.g. a CV against all jobs).

**This document is the frozen contract between the ingestion lane (embeds
jobs) and the matching lane (embeds CVs/queries).** Both sides must use the
same model and the same text composition, or the vectors are not comparable
and similarity scores are meaningless. Do not change anything in the
"Contract" section without agreeing it with the matching lane first.

## Contract

| Item | Value |
| --- | --- |
| **Model** | `all-MiniLM-L6-v2` (sentence-transformers) |
| **Vector size** | `384` (the model's output dimensionality) |
| **Distance metric** | `Cosine` |
| **Collection name** | `job_postings` |
| **Point ID** | `uuid5(NAMESPACE_URL, job_id)` |

The model is deliberately the *same one* `backend/features/matching/scorer.py`
already uses — not a second, independent choice.

### Text composition (exact)

The embedded text for a job posting is built by
`build_embedding_text()` in `backend/services/vector_store.py`:

```
Title: {title}
Skills: {skills, comma-joined}
Description: {description}
```

Three labelled lines, newline-joined, in that order. The labels and the
ordering are part of the contract — a query embedded without them will not sit
in the same region of vector space. `skills` is the canonical `JobPosting.skills`
list (real skills only; job-type/work-mode/seniority chips are held in their
own fields and are deliberately **not** part of the embedding).

**For the matching lane:** build your CV/query text the same way — a `Title:`
line (e.g. the person's current or target role), a `Skills:` line with their
skills comma-joined, and a `Description:` line (e.g. their summary) — then
encode it with `all-MiniLM-L6-v2` and search the `job_postings` collection.

### Why the point ID is a derived UUID

Qdrant requires point IDs to be an unsigned integer or a UUID. Our `job_id` is
a sha256-derived hex string, which is neither, so it cannot be used directly.
`uuid5(NAMESPACE_URL, job_id)` derives a valid UUID **deterministically**: the
same posting always maps to the same point, so re-ingesting it overwrites its
vector instead of creating a duplicate — mirroring the upsert-by-`job_id`
behaviour of the SQLite layer.

The real `job_id` is stored in the point payload, so any search hit maps
straight back to its row in the `job_postings` table.

### Payload fields

`job_id`, `title`, `company`, `location`, `url`, `source`.

`job_id` is the join key back to SQLite; the rest are there so a search result
can be displayed without a second database round-trip.

## How it fits the pipeline

SQLite stays the **source of truth** for dedup and run history. Qdrant is an
*additional* write target:

```
ingestion clients
      │
      ▼
upsert_job_postings ──► SQLite job_postings   (source of truth, dedup by job_id)
      │  (only after the batch is committed)
      ▼
sync_batch_to_vector_store ──► Qdrant job_postings collection (retrieval)
```

The vector sync runs **after** the SQLite batch is committed, so Qdrant can
never contain a posting that SQLite does not. It is wrapped in its own
try/except, matching the existing per-source failure isolation: if Qdrant is
unreachable (e.g. Docker isn't running), the run does **not** crash and the
SQLite writes are **not** discarded.

### Run status and the `jobs_embedded` counter

`IngestionRun` gains one additive column, `jobs_embedded` — chosen over a new
status value because it sits naturally beside the existing
`jobs_fetched` / `jobs_inserted` / `jobs_updated` / `jobs_skipped` counters and
leaves the `success` / `partial` / `failed` contract untouched. A lagging count
(`jobs_embedded` < inserted + updated) is itself the signal that the vector
store is behind.

Status semantics, unchanged except for one addition:

- `success` — all sources ingested **and** all embeddings synced.
- `partial` — some sources failed, **or** SQLite succeeded but the vector sync
  failed (details in `error_message`).
- `failed` — every source failed.

A vector-sync failure can only downgrade `success` → `partial`; it never yields
`failed`, because the authoritative write did succeed.

> **Schema note:** `jobs_embedded` is a new column, and `init_db()` uses
> `create_all`, which creates missing *tables* but does not add columns to
> existing ones. If you have an older local `career_coach.db`, delete it and
> let it be recreated (it's dev-only and git-ignored). There is no Alembic in
> the project yet.

## Running Qdrant

```bash
docker compose up -d qdrant
```

- REST API + dashboard: <http://localhost:6333/dashboard>
- gRPC: `localhost:6334`
- Data persists in the `qdrant_storage` named volume.

Connection settings come from the environment, defaulting to `localhost:6333`:

```
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

## Tests

`backend/tests/test_vector_store.py` uses qdrant-client's in-memory mode
(`QdrantClient(":memory:")`) and a stubbed model, so it needs neither Docker
nor a model download:

```bash
pytest backend/tests/test_vector_store.py -q
```

## Known dependency gap (not fixed here)

`backend/features/matching/scorer.py` on `main` imports `sentence-transformers`,
but that package is **missing from `requirements.txt` on `main`** — the matching
lane's own code will not import on a clean install. This branch adds the
dependency (pinned to `5.6.1`) because the vector store needs it too, but the
gap is flagged rather than silently patched around: the matching lane should
confirm the pinned version works for the scorer as well.
