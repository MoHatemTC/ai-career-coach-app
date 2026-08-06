from fastapi import FastAPI
from backend.routes.ingestion import router
from backend.services.database import init_db

app = FastAPI(title="Ingestion API (local viewing)")
init_db()
app.include_router(router)