from fastapi import FastAPI

from backend.routes.upload import router as upload_router
from backend.routes.matching import router as matching_router

app = FastAPI(
    title="AI Career Coach API",
    version="1.0"
)

app.include_router(upload_router)
app.include_router(matching_router, prefix="/api", tags=["Job Matching"])


@app.get("/")
def home():
    return {
        "message": "Welcome to AI Career Coach!"
    }