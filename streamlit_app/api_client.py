"""Thin HTTP wrappers around the FastAPI backend.

Mirrors the pattern already used in `ingestion_dashboard.py`: the backend URL
comes from BACKEND_HOST / BACKEND_PORT in .env, defaulting to localhost:8000,
and every call is a small function returning plain Python data. Keeping the
HTTP details here means the UI files never touch `requests` directly.

Everything is local — the backend runs on your machine, no hosted services.
"""

import os
import time
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


def _backend_error(prefix: str, exc: Exception, response=None) -> "BackendError":
    """Build an error that says *why*, not just which status code came back.

    FastAPI puts the real cause in the JSON body's `detail`, but
    `raise_for_status()` raises with only the status line, so a 503 surfaced as
    "Service Unavailable" and the actual reason (an unseeded collection, a
    missing key) was thrown away. This digs the detail back out.
    """
    detail = None
    if response is not None:
        try:
            body = response.json()
            detail = body.get("detail") if isinstance(body, dict) else None
        except ValueError:
            detail = (response.text or "").strip() or None
    return BackendError(f"{prefix}: {detail}" if detail else f"{prefix}: {exc}")


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
    email: str,
    phone: str,
    user_id: str = "default",
    channels: Optional[List[str]] = None,
    frequency: Optional[str] = None,
    relevance_threshold: Optional[float] = None,
) -> Dict:
    """POST notification settings; persisted to SQLite by the backend.

    Sends the Contract 6 shape (nested `contact` plus preferences). Omitted
    preferences are left as the backend already has them rather than blanked.
    """
    payload: Dict = {
        "user_id": user_id,
        "contact": {"email": email, "phone_whatsapp": phone},
    }
    if channels is not None:
        payload["notification_channels"] = channels
    if frequency is not None:
        payload["frequency"] = frequency
    if relevance_threshold is not None:
        payload["relevance_threshold"] = relevance_threshold

    response = None
    try:
        response = requests.post(
            _url("/notifications/settings"),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _backend_error("Saving settings failed", exc, response) from exc
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
    response = None
    try:
        response = requests.post(
            _url("/matching/pipeline"),
            json={"profile": profile, "top_k": top_k},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _backend_error("Matching failed", exc, response) from exc
    return response.json().get("ranked", [])


class ChatUnavailable(BackendError):
    """The conversational agent endpoint is not deployed on this backend."""


def chat(
    message: str, profile: Dict, history: Optional[List[Dict]] = None
) -> Dict:
    """Send a message to the conversational agent.

    Tries `POST /chat` first, which is the CV lane's agent, and falls back to
    `POST /conversation`, which serves the same
    `{intent, reply, updated_profile, run_pipeline}` contract. Preferring /chat
    means that lane takes over automatically once it is deployed, with no change
    here.

    Raises `ChatUnavailable` only if neither endpoint exists, which is the one
    case where the caller should drop to keyword routing.
    """
    payload = {"message": message, "profile": profile or {}}

    for path, body in (
        ("/chat", payload),
        ("/conversation", dict(payload, history=history or [])),
    ):
        try:
            response = requests.post(
                _url(path), json=body, timeout=DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            raise _backend_error("Chat failed", exc, None) from exc

        if response.status_code == 404:
            # This backend does not have that endpoint; try the next one.
            continue
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise _backend_error("Chat failed", exc, response) from exc
        return response.json()

    raise ChatUnavailable(
        "Neither /chat nor /conversation is available on this backend."
    )


def trigger_ingestion(
    sources: Optional[List[str]] = None, limit: int = 10
) -> int:
    """Kick off an ingestion run and return its id.

    The backend runs it as a background task and returns immediately, so the
    caller polls `get_ingestion_run` until the status leaves "running".
    """
    response = None
    try:
        response = requests.post(
            _url("/ingestion/run"),
            json={"sources": sources, "limit": limit},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _backend_error("Could not start ingestion", exc, response) from exc
    return response.json()["run_id"]


def get_ingestion_run(run_id: int) -> Dict:
    """Current status and counters for one ingestion run."""
    response = None
    try:
        response = requests.get(
            _url(f"/ingestion/runs/{run_id}"), timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _backend_error("Could not read ingestion run", exc, response) from exc
    return response.json()


# How long to wait for a background ingestion run before giving up and using
# whatever it has already committed. A poll budget, not a request timeout.
INGESTION_POLL_SECONDS = 90
INGESTION_POLL_INTERVAL = 1.0


def wait_for_ingestion(run_id: int, budget: float = None) -> Dict:
    """Poll an ingestion run until it finishes, or the budget runs out.

    Returns the last run payload seen. A run still `running` when the budget
    expires is returned as-is rather than raising: ingestion commits per
    source, so the jobs already written are usable and the caller should get on
    with matching instead of failing outright.
    """
    budget = INGESTION_POLL_SECONDS if budget is None else budget
    deadline = time.monotonic() + budget
    run = get_ingestion_run(run_id)
    while run.get("status") == "running" and time.monotonic() < deadline:
        time.sleep(INGESTION_POLL_INTERVAL)
        run = get_ingestion_run(run_id)
    return run


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
