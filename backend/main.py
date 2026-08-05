from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.features.matching.routes import router as matching_router
from backend.routes.ingestion import router as ingestion_router
from backend.routes.upload import router as upload_router
from backend.routes.profile import router as profile_router
from backend.routes.chat import router as chat_router
from backend.services.database import init_db
from backend.services.notification_scheduler import (
    start_scheduler,
    stop_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables on startup
    init_db()

    # Start notification scheduler
    start_scheduler()

    try:
        yield
    finally:
        # Stop scheduler when shutting down
        stop_scheduler()


app = FastAPI(
    title="AI Career Coach API",
    version="1.0",
    lifespan=lifespan,
)

app.include_router(matching_router, prefix="/matching", tags=["Matching"])
app.include_router(ingestion_router)
app.include_router(upload_router)
app.include_router(profile_router)
app.include_router(chat_router)


@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Career Coach API! The server is running."}