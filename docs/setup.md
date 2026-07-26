# Setup Guide

This project starts as a scaffold. Interns will add backend, frontend, and integration files as tasks are assigned.

## Requirements

- Git
- Python 3.11 or newer
- Node.js 20 or newer, when frontend implementation starts
- Docker, optional for local containers

## Local Setup

1. Clone the repository.
2. Copy `.env.example` to `.env`.
3. Read `CONTRIBUTING.md`.
4. Pick an assigned task.
5. Create only the files needed for that task.

## Backend Setup

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload
```

The API runs on <http://localhost:8000>, with interactive docs at `/docs`.

Note: the first run downloads the `all-MiniLM-L6-v2` sentence-transformer
model (~90MB) used by the matching scorer.

Run the tests with:

```bash
pytest backend/tests -q
```

## Frontend Setup

The v1 UI is Streamlit, per PRD 10.1 (a React app remains the stretch goal).

```bash
streamlit run frontend/src/streamlit_app.py
```

Serves on <http://localhost:8501>. Pages live in `frontend/src/pages/` and API
calls in `frontend/src/api/`. Set `API_BASE_URL` in `.env` if the backend is
not on `http://localhost:8000`.

## Environment Variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL. Defaults to local SQLite. |
| `APP_BASE_URL` | Public app URL, used in notification links. |
| `API_BASE_URL` | Where the Streamlit UI reaches the API. |
| `GEMINI_API_KEY` | CV parsing via `backend/services/llm_service.py`. |
| `NOTIFICATIONS_SCHEDULER_ENABLED` | Master switch for the daily digest. Off by default. |
| `POSTPEER_*` | WhatsApp delivery. See [`notifications.md`](notifications.md). |
| `EMAIL_*` | SMTP fallback delivery. |

With no `EMAIL_HOST` configured, digests print to the API console rather than
sending, so the full pipeline can be demoed without credentials.
