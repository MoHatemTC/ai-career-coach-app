from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.routes.upload import router as upload_router
from backend.routes.ingestion import router as ingestion_router
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

app.include_router(upload_router)
app.include_router(ingestion_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to AI Career Coach!"
    }
