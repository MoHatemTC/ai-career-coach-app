"""Database engine, session factory, and table creation.

Reads `DATABASE_URL` from the environment (via `python-dotenv`, matching the
convention in `llm_service.py`). Defaults to the project's SQLite database.
SQLite is deliberate for this stage — zero-setup and file-based, adequate for
internal ingestion volumes. The same SQLAlchemy layer swaps to PostgreSQL
later by changing only `DATABASE_URL`.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.db_models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_coach.db")

# check_same_thread=False is required for SQLite under FastAPI, where the
# request thread and the BackgroundTasks thread differ. It is a no-op for
# non-SQLite URLs.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables if they do not yet exist. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
