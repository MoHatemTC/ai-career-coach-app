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
    """The agreed shape: nested contact, plus channels/frequency/threshold.

    Since delivery landed the payload also carries three scheduling fields —
    `full_name`, `send_hour_local`, `timezone` — which a scheduled digest needs
    because it has no browser session to ask who this is or when their morning
    is. They are additive: a client that omits them on write keeps what is
    stored, and a client that ignores them on read is unaffected.

    Asserted as whole-payload equality on purpose. This is a contract another
    lane reads, and a field appearing or vanishing unannounced is exactly what
    this test exists to catch.
    """
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
        "full_name": None,
        "send_hour_local": 8,
        "timezone": "Africa/Cairo",
    }


def test_scheduling_fields_round_trip(client):
    """The scheduler reads these to decide *when* a user's digest goes out, so
    a value that does not survive the round trip delivers at the wrong hour."""
    client.post(
        "/notifications/settings",
        json={
            "user_id": "default",
            "email": "omar@example.com",
            "full_name": "Omar Zahran",
            "send_hour_local": 19,
            "timezone": "Europe/London",
        },
    )

    body = client.get("/notifications/settings/default").json()

    assert body["full_name"] == "Omar Zahran"
    assert body["send_hour_local"] == 19
    assert body["timezone"] == "Europe/London"


def test_an_unknown_timezone_is_rejected_on_write(client):
    """A zone ZoneInfo cannot load, once stored, turns one bad form value into
    a digest that silently goes out at the wrong local hour forever."""
    response = client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "a@b.com", "timezone": "Mars/Olympus"},
    )

    assert response.status_code == 422


def test_an_out_of_range_send_hour_is_rejected(client):
    response = client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "a@b.com", "send_hour_local": 25},
    )

    assert response.status_code == 422


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


def test_a_preferences_only_save_does_not_erase_the_contact(client):
    """The mirror of the test above, and the one that was missing.

    Preferences were protected from a contact-only save, but contact was not
    protected from a preferences-only save: `row.email` was assigned
    unconditionally, so `{"relevance_threshold": 0.3}` silently destroyed the
    only stored copy of the user's address. The React form always sends contact,
    which is exactly why this went unnoticed.
    """
    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "omar@example.com", "phone": "+20100"},
    )

    client.post(
        "/notifications/settings",
        json={"user_id": "default", "relevance_threshold": 0.3},
    )

    body = client.get("/notifications/settings/default").json()
    assert body["contact"]["email"] == "omar@example.com"
    assert body["contact"]["phone_whatsapp"] == "+20100"
    assert body["relevance_threshold"] == 0.3


def test_an_explicit_null_still_clears_the_contact(client):
    """"Omitted" means keep; "sent as null" still means clear. Losing that
    distinction would leave no way to remove an address."""
    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "omar@example.com", "phone": "+20100"},
    )

    client.post(
        "/notifications/settings",
        json={"user_id": "default", "contact": {"email": None, "phone_whatsapp": None}},
    )

    body = client.get("/notifications/settings/default").json()
    assert body["contact"] == {"email": None, "phone_whatsapp": None}


def test_a_partial_contact_leaves_the_other_half_alone(client):
    client.post(
        "/notifications/settings",
        json={"user_id": "default", "email": "omar@example.com", "phone": "+20100"},
    )

    client.post(
        "/notifications/settings",
        json={"user_id": "default", "contact": {"email": "new@example.com"}},
    )

    body = client.get("/notifications/settings/default").json()
    assert body["contact"]["email"] == "new@example.com"
    assert body["contact"]["phone_whatsapp"] == "+20100"


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
