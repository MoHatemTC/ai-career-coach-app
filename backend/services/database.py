"""Database engine, session factory, and table creation.

Reads `DATABASE_URL` from the environment (via `python-dotenv`, matching the
convention in `llm_service.py`). Defaults to the project's SQLite database.
SQLite is deliberate for this stage — zero-setup and file-based, adequate for
internal ingestion volumes. The same SQLAlchemy layer swaps to PostgreSQL
later by changing only `DATABASE_URL`.
"""

import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend.models.db_models import Base

logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_coach.db")

# check_same_thread=False is required for SQLite under FastAPI, where the
# request thread and the BackgroundTasks thread differ. It is a no-op for
# non-SQLite URLs.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Columns added to existing tables after they were first created. `create_all`
# only ever CREATEs — it never ALTERs — so a developer with a `career_coach.db`
# from before these landed would get "no such column" on every read of that
# table. There is no Alembic in this project, and adding one for four nullable
# columns is not proportionate; an additive ALTER is.
#
# Additive only, by design: no drops, no type changes, no renames. Anything
# that cannot be expressed as "add a nullable column" needs a real migration
# tool, and that is the point at which to introduce one.
_ADDED_COLUMNS = {
    "notification_settings": {
        "full_name": "VARCHAR",
        "send_hour_local": "INTEGER",
        "timezone": "VARCHAR",
        "profile_snapshot": "TEXT",
    },
}


def _apply_additive_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            # create_all just made it with every column present.
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name in present:
                continue
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                )
            logger.info("Added column %s.%s", table, name)


def init_db() -> None:
    """Create all tables if they do not yet exist. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
