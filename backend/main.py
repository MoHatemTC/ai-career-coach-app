from fastapi import FastAPI
from backend.features.matching.routes import router

app = FastAPI(title="AI Career Coach API")


app.include_router(router, prefix="/matching", tags=["Matching"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Career Coach API! The server is running."}