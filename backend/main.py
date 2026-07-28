from fastapi import FastAPI

from backend.database import Base, engine
from backend.models.profile import Profile

from backend.routes.upload import router as upload_router
from backend.routes.profile import router as profile_router
from backend.routes.chat import router as chat_router
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Career Coach API",
    version="1.0"
)

app.include_router(upload_router)
app.include_router(profile_router)
app.include_router(chat_router)


@app.get("/")
def home():
    return {"message": "Welcome to AI Career Coach!"}