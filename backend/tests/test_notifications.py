"""Route tests for the notification settings endpoints.

These pin Contract 6 from the pipeline plan: the shape the notifications lane
reads. Uses an in-memory SQLite database via FastAPI's dependency override, so
they run without touching the developer's real `career_coach.db`.
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


# --- Contract 6 shape --------------------------------------------------------


def test_response_matches_contract_6(client):
    """The agreed shape: nested contact, plus channels/frequency/threshold."""
    client.post(
        "/notifications/settings",
        json={
            "user_id": "default",
            "contact": {"email": "omar@example.com",
                        "phone_whatsapp": "+201001234567"},
            "notification_channels": ["email", "whatsapp"],
            "frequency": "daily",
            "relevance_threshold": 0.75,
        },
    )

    body = client.get("/notifications/settings/default").json()

    assert body == {
        "user_id": "default",
        "contact": {"email": "omar@example.com",
                    "phone_whatsapp": "+201001234567"},
        "notification_channels": ["email", "whatsapp"],
        "frequency": "daily",
        "relevance_threshold": 0.75,
    }


def test_flat_payload_is_still_accepted(client):
    """The Streamlit settings form posts flat email/phone; breaking it for the
    sake of the nested shape would be gratuitous."""
    saved = client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "omar@example.com",
              "phone": "+20100"},
    )

    assert saved.status_code == 200
    assert saved.json()["contact"] == {
        "email": "omar@example.com", "phone_whatsapp": "+20100"
    }


def test_nested_contact_wins_over_flat(client):
    saved = client.post(
        "/notifications/settings",
        json={
            "user_id": "default",
            "email": "flat@example.com",
            "contact": {"email": "nested@example.com"},
        },
    )

    assert saved.json()["contact"]["email"] == "nested@example.com"


def test_preferences_default_so_a_new_row_is_a_valid_payload(client):
    """A contact-only save must still produce a complete Contract 6 object,
    otherwise the notifications lane has to guess the defaults."""
    body = client.post(
        "/notifications/settings", json={"email": "omar@example.com"}
    ).json()

    assert body["notification_channels"] == ["email"]
    assert body["frequency"] == "daily"
    assert body["relevance_threshold"] == 0.75


def test_contact_only_save_does_not_reset_preferences(client):
    """The UI form sends only contact fields. Blanking the preferences it does
    not know about would silently undo the user's choices."""
    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "a@b.com",
              "notification_channels": ["whatsapp"], "frequency": "weekly",
              "relevance_threshold": 0.5},
    )

    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "changed@b.com"},
    )

    body = client.get("/notifications/settings/default").json()
    assert body["contact"]["email"] == "changed@b.com"
    assert body["notification_channels"] == ["whatsapp"]
    assert body["frequency"] == "weekly"
    assert body["relevance_threshold"] == 0.5


# --- persistence behaviour ---------------------------------------------------


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
    assert fetched["contact"]["email"] == "second@example.com"
    assert fetched["contact"]["phone_whatsapp"] == "+2"


def test_settings_are_per_user(client):
    client.post(
        "/notifications/settings",
        json={"user_id": "alice", "email": "alice@example.com", "phone": "+1"},
    )
    client.post(
        "/notifications/settings",
        json={"user_id": "bob", "email": "bob@example.com", "phone": "+2"},
    )

    alice = client.get("/notifications/settings/alice").json()
    bob = client.get("/notifications/settings/bob").json()
    assert alice["contact"]["email"] == "alice@example.com"
    assert bob["contact"]["email"] == "bob@example.com"


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
    """Both are nullable, so a partially-filled form still saves."""
    response = client.post(
        "/notifications/settings", json={"user_id": "default", "email": "a@b.com"}
    )
    assert response.status_code == 200
    assert response.json()["contact"]["phone_whatsapp"] is None
