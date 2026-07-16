from fastapi import FastAPI

from backend.routes.upload import router as upload_router

app = FastAPI(
    title="AI Career Coach API",
    version="1.0"
)

app.include_router(upload_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to AI Career Coach!"
    }