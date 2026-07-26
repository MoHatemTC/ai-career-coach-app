# Sprints Career Coach

AI-powered career coach for helping learners analyze their CVs, find relevant jobs, understand skill gaps, and prepare application materials.

This repository is intentionally a learning scaffold. It provides the project structure, documentation, contribution rules, and collaboration workflow. Interns should create the actual feature files as part of their assigned tasks.

## Project Areas

- `backend/` - API, business logic, prompts, data models, and tests.
- `frontend/` - user interface.
- `data/` - sample CVs, profiles, and job data for local development.
- `docs/` - product, setup, architecture, deployment, and workflow documentation.
- `scripts/` - helper scripts for setup, testing, and local tasks.

## Running it locally

```bash
pip install -r requirements.txt
cp .env.example .env

# Terminal 1 — API (http://localhost:8000, docs at /docs)
uvicorn backend.main:app --reload

# Terminal 2 — UI (http://localhost:8501)
streamlit run frontend/src/streamlit_app.py
```

## Features

- **CV upload & parsing** — `backend/routes/upload.py`
- **Job ingestion** — `backend/services/ingestion.py`
- **Matching & ranking** — `backend/features/matching/`
- **Daily top-3 match notifications** — `backend/features/notifications/`
  ([docs](docs/notifications.md))

## First Steps

1. Read `docs/PRD.md`.
2. Read `docs/architecture.md`.
3. Read `CONTRIBUTING.md`.
4. Pick a task from `docs/tasks.md`.
5. Create a branch and open a pull request when ready.

## Important Rule

Do not add large feature code directly to `main`. Every change should go through a branch and pull request.
