from fastapi import FastAPI

from backend.routes.upload import router as upload_router
# 1. استيراد الـ Router الجديد الخاص بالمطابقة اللي لسه عاملينه
from backend.routes.matching import router as matching_router

app = FastAPI(
    title="AI Career Coach API",
    version="1.0"
)

# 2. تسجيل الـ Router القديم
app.include_router(upload_router)

# 3. تسجيل الـ Router الجديد عشان السيرفر يقراه
app.include_router(matching_router, prefix="/api", tags=["Job Matching"])


@app.get("/")
def home():
    return {
        "message": "Welcome to AI Career Coach!"
    }