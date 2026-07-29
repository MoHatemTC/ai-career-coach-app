"""Thin HTTP wrappers around the FastAPI backend.

Mirrors the pattern already used in `ingestion_dashboard.py`: the backend URL
comes from BACKEND_HOST / BACKEND_PORT in .env, defaulting to localhost:8000,
and every call is a small function returning plain Python data. Keeping the
HTTP details here means the UI files never touch `requests` directly.

Everything is local — the backend runs on your machine, no hosted services.
"""

import os
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TIMEOUT = 60  # CV parsing can take a while


def backend_base_url() -> str:
    """Resolve the backend URL, mapping the 0.0.0.0 bind address to loopback."""
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = os.getenv("BACKEND_PORT", "8000")
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


BASE_URL = backend_base_url()


class BackendError(Exception):
    """The backend could not be reached, or returned an error."""


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


def health_check() -> Tuple[bool, str]:
    """Is the backend up? Returns (ok, message) so the UI can show a banner."""
    try:
        response = requests.get(_url("/"), timeout=5)
        response.raise_for_status()
        return True, "Backend is up."
    except requests.RequestException as exc:
        return False, f"Cannot reach the backend at {BASE_URL}: {exc}"


def upload_cv(file_name: str, file_bytes: bytes) -> Dict:
    """POST a CV to the REAL /upload endpoint and return the parsed profile.

    The backend runs the actual CV parser and profile extraction; nothing here
    is mocked.
    """
    try:
        response = requests.post(
            _url("/upload"),
            files={"file": (file_name, file_bytes)},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BackendError(f"CV upload failed: {exc}") from exc

    payload = response.json()
    # The endpoint returns {"message", "filename", "profile"}; the profile is
    # what the UI edits. Fall back to the whole body if the shape changes.
    profile = payload.get("profile", payload)
    if isinstance(profile, str):
        # Some LLM paths return a JSON string rather than an object.
        import json

        try:
            profile = json.loads(profile)
        except json.JSONDecodeError:
            profile = {"summary": profile}
    return profile or {}


def save_notification_settings(
    email: str, phone: str, user_id: str = "default"
) -> Dict:
    """POST notification settings; persisted to SQLite by the backend."""
    try:
        response = requests.post(
            _url("/notifications/settings"),
            json={"user_id": user_id, "email": email, "phone": phone},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BackendError(f"Saving settings failed: {exc}") from exc
    return response.json()


def get_notification_settings(user_id: str = "default") -> Optional[Dict]:
    """GET saved settings, or None if none have been saved yet."""
    try:
        response = requests.get(
            _url(f"/notifications/settings/{user_id}"), timeout=DEFAULT_TIMEOUT
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BackendError(f"Loading settings failed: {exc}") from exc
    return response.json()


def run_match_pipeline(profile: Dict, top_k: int = 10) -> List[Dict]:
    """POST a profile to the REAL /matching/pipeline endpoint.

    Runs vector retrieval and LLM re-ranking backend-side and returns the
    re-ranker's ranking: dicts of {job_id, rank, fit_score, job_data}.
    Nothing here is mocked.

    This has to go over HTTP rather than importing the pipeline directly:
    embedded Qdrant (QDRANT_MODE=local) allows a single process at a time, and
    the backend already holds that lock.
    """
    try:
        response = requests.post(
            _url("/matching/pipeline"),
            json={"profile": profile, "top_k": top_k},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BackendError(f"Matching failed: {exc}") from exc
    return response.json().get("ranked", [])


def list_persisted_jobs(limit: int = 20, offset: int = 0) -> List[Dict]:
    """GET persisted job postings (used for context/debugging in the UI)."""
    try:
        response = requests.get(
            _url("/ingestion/jobs"),
            params={"limit": limit, "offset": offset},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise BackendError(f"Loading jobs failed: {exc}") from exc
    return response.json()
