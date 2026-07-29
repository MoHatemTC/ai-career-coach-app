from contextlib import asynccontextmanager

from fastapi import FastAPI
from backend.features.matching.routes import router as matching_router
from backend.routes.ingestion import router as ingestion_router
from backend.routes.notifications import router as notifications_router
from backend.routes.upload import router as upload_router
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

app.include_router(matching_router, prefix="/matching", tags=["Matching"])
app.include_router(ingestion_router)
app.include_router(notifications_router)
app.include_router(upload_router)


@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Career Coach API! The server is running."}
