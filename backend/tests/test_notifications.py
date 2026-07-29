"""Route tests for the notification settings endpoints.

Uses an in-memory SQLite database via FastAPI's dependency override, so these
run without touching the developer's real `career_coach.db`.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db_models import Base
from backend.routes.notifications import router
from backend.services.database import get_db


@pytest.fixture
def client():
    # StaticPool keeps every connection on the SAME in-memory database;
    # without it the dependency's session opens a fresh, tableless one.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_get_settings_404_when_never_saved(client):
    """The UI relies on this 404 to render an empty form on first use."""
    response = client.get("/notifications/settings/default")
    assert response.status_code == 404


def test_save_then_read_round_trip(client):
    saved = client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "omar@example.com", "phone": "+20100"},
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "user_id": "default",
        "email": "omar@example.com",
        "phone": "+20100",
    }

    # Read back through the endpoint the notifications lane will use.
    fetched = client.get("/notifications/settings/default")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "omar@example.com"
    assert fetched.json()["phone"] == "+20100"


def test_saving_twice_updates_rather_than_duplicating(client):
    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "first@example.com", "phone": "+1"},
    )
    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "second@example.com", "phone": "+2"},
    )

    fetched = client.get("/notifications/settings/default").json()
    assert fetched["email"] == "second@example.com"
    assert fetched["phone"] == "+2"


def test_settings_are_per_user(client):
    client.post(
        "/notifications/settings",
        json={"user_id": "alice", "email": "alice@example.com", "phone": "+1"},
    )
    client.post(
        "/notifications/settings",
        json={"user_id": "bob", "email": "bob@example.com", "phone": "+2"},
    )

    assert client.get("/notifications/settings/alice").json()["email"] == "alice@example.com"
    assert client.get("/notifications/settings/bob").json()["email"] == "bob@example.com"


def test_user_id_defaults_when_omitted(client):
    """The UI posts without a user_id; it must land under 'default'."""
    response = client.post(
        "/notifications/settings",
        json={"email": "nouser@example.com", "phone": "+20"},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "default"
    assert client.get("/notifications/settings/default").status_code == 200


def test_email_and_phone_are_optional(client):
    """Both fields are nullable, so a partially-filled form still saves."""
    response = client.post(
        "/notifications/settings", json={"user_id": "default", "email": "a@b.com"}
    )
    assert response.status_code == 200
    assert response.json()["phone"] is None
