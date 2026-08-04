import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.features.matching.routes import router as matching_router
from backend.routes.conversation import router as conversation_router
from backend.routes.ingestion import router as ingestion_router
from backend.routes.notifications import router as notifications_router
from backend.routes.upload import router as upload_router
from backend.routes.skill_gap import router as skill_gap_router
from backend.routes.job_insight import router as job_insight_router
from backend.services.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables on startup (no-op if they already exist).
    init_db()
    yield


app = FastAPI(
    title="AI Career Coach API",
    version="1.0",
    lifespan=lifespan,
)


def allowed_origins() -> list[str]:
    """Origins the browser frontend may call from.

    Streamlit never needed this: it renders server-side and its HTTP calls come
    from Python, not a browser. The React app does, and without it every request
    fails the preflight with a message that names CORS but not which origin to
    add, which is a bad first ten minutes for anyone cloning the repo.

    The Vite dev server is allowed by default so `npm run dev` works with no
    configuration. Set CORS_ORIGINS (comma separated) for anything else.
    """
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matching_router, prefix="/matching", tags=["Matching"])
app.include_router(conversation_router)
app.include_router(ingestion_router)
app.include_router(notifications_router)
app.include_router(upload_router)
app.include_router(skill_gap_router)
app.include_router(job_insight_router)


@app.get("/")
def read_root():
    return {
        "message": "Welcome to the AI Career Coach API! The server is running."
    }
