import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.features.matching.routes import router as matching_router
from backend.features.notifications.routes import router as notifications_router
from backend.features.notifications.scheduler import shutdown_scheduler, start_scheduler
from backend.routes.ingestion import router as ingestion_router
from backend.routes.upload import router as upload_router
from backend.services.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # No-op unless NOTIFICATIONS_SCHEDULER_ENABLED=true, so importing this app
    # in tests or a dev shell never sends real messages.
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="AI Career Coach API",
    version="1.0",
    lifespan=lifespan,
)

# The Streamlit settings UI calls this API from a different origin
# (localhost:8501 -> localhost:8000), so the browser preflights every request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO(Omar Zahran): restrict before any public deploy.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matching_router, prefix="/matching", tags=["Matching"])
app.include_router(notifications_router)
app.include_router(ingestion_router)
app.include_router(upload_router)


@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Career Coach API! The server is running."}
