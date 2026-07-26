"""Thin HTTP client for the Career Coach API.

Lives in frontend/src/api/ per docs/architecture.md ("frontend/src/api/ -
backend API calls"). Keeping every request in one module means the UI pages
never build URLs themselves, so a route change is a one-file edit.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
DEFAULT_TIMEOUT = int(os.getenv("API_TIMEOUT_SECONDS", "30"))


class ApiError(Exception):
    """A failed API call, carrying a message fit to show a user.

    FastAPI returns validation problems as a 422 whose `detail` is a list of
    per-field objects. Rendering that raw is unreadable, so it is flattened
    into "field: message" lines here — the settings form shows this directly.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _readable_error(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"

    if isinstance(detail, list):
        lines = []
        for item in detail:
            location = item.get("loc") or []
            # Drop the "body" prefix FastAPI always adds.
            field = ".".join(str(part) for part in location if part != "body")
            lines.append(f"{field}: {item.get('msg', 'invalid')}" if field else item.get("msg", "invalid"))
        return "\n".join(lines)

    if isinstance(detail, str):
        return detail
    return f"HTTP {response.status_code}"


def _request(method: str, path: str, **kwargs) -> Any:
    url = f"{API_BASE_URL}{path}"
    try:
        response = requests.request(method, url, timeout=DEFAULT_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(
            f"Could not reach the API at {API_BASE_URL}.\n"
            f"Is it running? Start it with: uvicorn backend.main:app --reload\n\n{exc}"
        ) from exc

    if response.status_code == 204:
        return None
    if response.status_code >= 400:
        raise ApiError(_readable_error(response), response.status_code)

    try:
        return response.json()
    except ValueError:
        return None


def health() -> bool:
    try:
        _request("GET", "/")
        return True
    except ApiError:
        return False


# --- Users & settings ------------------------------------------------------


def list_users(only_enabled: bool = False) -> list[dict]:
    return _request("GET", "/notifications/users", params={"only_enabled": only_enabled})


def get_user(user_id: str) -> Optional[dict]:
    try:
        return _request("GET", f"/notifications/users/{user_id}")
    except ApiError as exc:
        if exc.status_code == 404:
            return None
        raise


def create_user(payload: dict) -> dict:
    return _request("POST", "/notifications/users", json=payload)


def update_settings(user_id: str, patch: dict) -> dict:
    return _request("PATCH", f"/notifications/users/{user_id}/settings", json=patch)


def update_profile(user_id: str, profile: dict) -> dict:
    return _request("PUT", f"/notifications/users/{user_id}/profile", json=profile)


def delete_user(user_id: str) -> None:
    _request("DELETE", f"/notifications/users/{user_id}")


# --- Digest ----------------------------------------------------------------


def preview_matches(user_id: str, top_n: int = 3, include_recent: bool = True) -> list[dict]:
    return _request(
        "GET",
        f"/notifications/users/{user_id}/preview",
        params={"top_n": top_n, "include_recent": include_recent},
    )


def send_test(user_id: str, dry_run: bool = False) -> dict:
    return _request(
        "POST",
        f"/notifications/users/{user_id}/send-test",
        params={"dry_run": dry_run},
    )


# --- Diagnostics -----------------------------------------------------------


def provider_status() -> list[dict]:
    return _request("GET", "/notifications/providers")


def scheduler_status() -> dict:
    return _request("GET", "/notifications/scheduler")


def recent_logs(user_id: Optional[str] = None, limit: int = 20) -> list[dict]:
    params: dict = {"limit": limit}
    if user_id:
        params["user_id"] = user_id
    return _request("GET", "/notifications/logs", params=params)
