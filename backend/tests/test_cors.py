"""CORS has to be configured, or the React frontend cannot call the API at all.

Streamlit never needed it: it renders server-side and its HTTP calls come from
Python. A browser client does, and the failure mode is a preflight rejection
that names CORS without naming the origin to add.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

DEV_ORIGIN = "http://localhost:5173"


@pytest.fixture
def client():
    from backend import main

    return TestClient(main.app)


def test_the_vite_dev_origin_is_allowed_out_of_the_box(client):
    """`npm run dev` must work with no configuration."""
    response = client.options(
        "/notifications/settings/default",
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_a_simple_request_carries_the_allow_origin_header(client):
    response = client.get("/", headers={"Origin": DEV_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_an_unlisted_origin_is_not_allowed(client):
    """Reflecting any origin would defeat the point of configuring this."""
    response = client.get("/", headers={"Origin": "https://not-ours.example"})

    assert "access-control-allow-origin" not in response.headers


def test_configured_origins_replace_the_defaults(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://coach.example,https://staging.example")

    from backend import main

    importlib.reload(main)
    try:
        assert main.allowed_origins() == [
            "https://coach.example",
            "https://staging.example",
        ]
    finally:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        importlib.reload(main)


def test_blank_configuration_falls_back_to_the_dev_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "   ")

    from backend import main

    assert DEV_ORIGIN in main.allowed_origins()


def test_the_post_endpoints_the_frontend_uses_accept_a_preflight(client):
    """Upload and the pipeline are POSTs with a JSON or multipart body, so they
    are preflighted rather than simple requests."""
    for path in ("/upload", "/matching/pipeline", "/notifications/settings"):
        response = client.options(
            path,
            headers={
                "Origin": DEV_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200, path
        assert response.headers["access-control-allow-origin"] == DEV_ORIGIN, path
