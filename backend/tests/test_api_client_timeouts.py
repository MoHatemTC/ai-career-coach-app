"""The UI's HTTP budgets have to outlast the backend's own ceilings.

`POST /matching/pipeline` is not one model call, it is four in sequence: a
ranking pass plus an explanation for each returned job. Each is bounded
backend-side by LLM_TIMEOUT_SECONDS. A flat 60-second client budget therefore
fired first and reported

    Matching failed: HTTPConnectionPool(host='127.0.0.1', port=8000):
    Read timed out. (read timeout=60)

for a run that had not failed and was still working. A client timeout shorter
than the work it is waiting on reports failures that did not happen.
"""

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UI_DIR = REPO_ROOT / "streamlit_app"


@pytest.fixture
def api_client(monkeypatch):
    """Import the real streamlit_app/api_client.py, reloaded per test."""
    monkeypatch.syspath_prepend(str(UI_DIR))
    sys.modules.pop("api_client", None)
    module = importlib.import_module("api_client")
    yield module
    sys.modules.pop("api_client", None)


def test_the_pipeline_budget_covers_every_call_it_waits_on(api_client):
    per_call = api_client.PIPELINE_MODEL_CALLS * 45.0

    assert api_client.PIPELINE_TIMEOUT > per_call


def test_the_pipeline_budget_beats_the_old_flat_sixty(api_client):
    """60s was the value that produced the reported failure."""
    assert api_client.PIPELINE_TIMEOUT > 60


def test_the_pipeline_counts_the_calls_the_backend_actually_makes(api_client):
    """One ranking pass plus one explanation per job in top_3."""
    assert api_client.PIPELINE_MODEL_CALLS == 4


def test_the_budget_follows_the_backend_ceiling(monkeypatch):
    """Raising the per-call ceiling must raise the client budget with it, or
    the two drift apart again."""
    monkeypatch.syspath_prepend(str(UI_DIR))
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "90")
    monkeypatch.delenv("PIPELINE_TIMEOUT_SECONDS", raising=False)
    sys.modules.pop("api_client", None)
    try:
        module = importlib.import_module("api_client")
        assert module.PIPELINE_TIMEOUT > 4 * 90
    finally:
        sys.modules.pop("api_client", None)


def test_an_explicit_budget_wins(monkeypatch):
    monkeypatch.syspath_prepend(str(UI_DIR))
    monkeypatch.setenv("PIPELINE_TIMEOUT_SECONDS", "123")
    sys.modules.pop("api_client", None)
    try:
        module = importlib.import_module("api_client")
        assert module.PIPELINE_TIMEOUT == 123.0
    finally:
        sys.modules.pop("api_client", None)


def test_chat_gets_headroom_over_a_single_call(api_client):
    """One model call, not four, so it does not need the pipeline's budget —
    but it still has to outlast one ceiling."""
    assert api_client.CHAT_TIMEOUT > 45
    assert api_client.CHAT_TIMEOUT < api_client.PIPELINE_TIMEOUT


def test_the_pipeline_request_uses_the_pipeline_budget(api_client, monkeypatch):
    """The constant existing is not the fix; the call site has to use it."""
    captured = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ranked": []}

    def _post(url, **kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(api_client.requests, "post", _post)

    api_client.run_match_pipeline({"skills": ["python"]})

    assert captured["timeout"] == api_client.PIPELINE_TIMEOUT
