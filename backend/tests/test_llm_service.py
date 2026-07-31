"""Tests for CV profile extraction.

The provider is substituted, so nothing here needs a key or a network call.
These cover the parsing contract rather than the prompt: what `extract_profile`
does with what the model hands back, including the shapes that used to reach the
user as an ASGI traceback.
"""

import json

import pytest

from backend.services.llm_service import extract_profile


def _returns(text, reason=None):
    """Substitute the provider with one that answers `text`."""
    return lambda *args, **kwargs: (text, reason)


PROFILE = {
    "name": "Omar Zahran",
    "email": "omar@example.com",
    "phone": "+20100000000",
    "skills": ["python", "fastapi"],
    "education": ["BSc Computer Science"],
    "experience": ["Intern, Sprints"],
}


def test_a_clean_json_reply_is_parsed(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason",
        _returns(json.dumps(PROFILE)),
    )

    assert extract_profile("some cv text") == PROFILE


def test_a_fenced_reply_is_unwrapped(monkeypatch):
    """Models add ```json fences even when asked for raw JSON."""
    fenced = f"```json\n{json.dumps(PROFILE)}\n```"
    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason", _returns(fenced)
    )

    assert extract_profile("some cv text") == PROFILE


def test_the_cv_text_reaches_the_prompt(monkeypatch):
    captured = {}

    def _complete(prompt, **kwargs):
        captured["prompt"] = prompt
        return json.dumps(PROFILE), None

    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason", _complete
    )

    extract_profile("Omar worked on retrieval pipelines")

    assert "Omar worked on retrieval pipelines" in captured["prompt"]


def test_json_mode_is_requested(monkeypatch):
    captured = {}

    def _complete(prompt, **kwargs):
        captured.update(kwargs)
        return json.dumps(PROFILE), None

    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason", _complete
    )

    extract_profile("cv")

    assert captured["response_mime_type"] == "application/json"


def test_truncated_json_raises_with_the_models_output(monkeypatch):
    """This was a raw JSONDecodeError and a 500: "Unterminated string starting
    at line 6 column 9" tells you a character offset and nothing about what to
    change. The output itself is the evidence, so it belongs in the message."""
    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason",
        _returns('{\n  "name": "Omar",\n  "skills": ["pyth'),
    )

    with pytest.raises(RuntimeError) as excinfo:
        extract_profile("cv")

    assert "not valid JSON" in str(excinfo.value)
    assert "Omar" in str(excinfo.value)


def test_prose_instead_of_json_raises_rather_than_crashing(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason",
        _returns("Sure! Here is the candidate's profile:"),
    )

    with pytest.raises(RuntimeError, match="not valid JSON"):
        extract_profile("cv")


def test_a_failed_call_reports_the_providers_reason(monkeypatch):
    """The gateway's own words must survive. A 403 naming the model was being
    reported as "check the URL and the key", both of which were correct."""
    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason",
        _returns(None, "the gateway rejected model 'kimi-k2.5': team not "
                       "allowed to access model"),
    )

    with pytest.raises(RuntimeError) as excinfo:
        extract_profile("cv")

    assert "kimi-k2.5" in str(excinfo.value)
    assert "team not allowed" in str(excinfo.value)


def test_the_error_is_a_runtimeerror_so_upload_can_return_503(monkeypatch):
    """backend/routes/upload.py catches RuntimeError specifically. A different
    exception type there would go back to being an unhandled 500."""
    monkeypatch.setattr(
        "backend.services.llm_service.complete_with_reason",
        _returns("not json at all"),
    )

    with pytest.raises(RuntimeError):
        extract_profile("cv")
