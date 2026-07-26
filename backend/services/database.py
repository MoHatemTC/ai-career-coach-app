import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# .env.example already documents DATABASE_URL; it was previously ignored and
# the sqlite path was hardcoded. Reading it here means the scheduler and the
# API can be pointed at the same Postgres instance in deployment without a
# code change (PRD 10.1).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_coach.db")

_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Columns added to `job_postings` after the table already existed in local dev
# databases. SQLAlchemy's create_all() only CREATEs missing tables — it never
# ALTERs an existing one — so without this every developer with a pre-existing
# career_coach.db would hit "no such column" at runtime.
#
# This is a deliberately minimal stand-in for a real migration tool. When the
# project moves to Postgres (PRD 10.1), replace it with Alembic.
_ADDITIVE_COLUMNS = {
    "job_postings": {
        "skills": "JSON",
        "job_type": "VARCHAR",
        "work_mode": "VARCHAR",
        "career_level": "VARCHAR",
        "experience_years_raw": "VARCHAR",
        "salary_text": "VARCHAR",
        "source": "VARCHAR",
        "url": "VARCHAR",
        "date": "DATETIME",
    },
}


def _apply_additive_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all() will build it with every column.

            present = {col["name"] for col in inspector.get_columns(table)}
            for column_name, column_type in columns.items():
                if column_name in present:
                    continue
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
                )


def init_db():
    # Importing the module registers every ORM class on Base.metadata. Without
    # this the users / notification_logs tables are silently never created.
    from backend.models import db_models  # noqa: F401

    _apply_additive_columns()
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
