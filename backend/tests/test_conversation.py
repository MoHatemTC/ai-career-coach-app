"""Tests for the conversational layer.

Gemini is substituted throughout, so nothing here needs a key or a network.
What matters is the contract and the degradation: the chat must never go down
or lose the user's profile because the model misbehaved.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import conversation
from backend.services.conversation import INTENTS, respond

PROFILE = {"name": "Omar", "title": "Backend Developer", "skills": ["python"]}


def _reply(**overrides):
    body = {
        "intent": "other",
        "reply": "Hello.",
        "updated_profile": PROFILE,
        "run_pipeline": False,
    }
    body.update(overrides)
    return json.dumps(body)


def _stub_gemini(monkeypatch, value):
    calls = []

    def _call(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return value() if callable(value) else value

    monkeypatch.setattr(conversation, "call_gemini", _call)
    return calls


# --- the happy path ----------------------------------------------------------


def test_reply_is_returned(monkeypatch):
    _stub_gemini(monkeypatch, _reply(reply="Nice to meet you, Kabulo."))

    result = respond("my name is actually Kabulo", PROFILE)

    assert result["reply"] == "Nice to meet you, Kabulo."
    assert result["intent"] in INTENTS


def test_profile_and_history_reach_the_prompt(monkeypatch):
    """Without the profile and the recent turns it cannot hold a conversation,
    which is the whole point of not using keyword matching."""
    calls = _stub_gemini(monkeypatch, _reply())
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    respond("what are my skills?", PROFILE, history)

    prompt = calls[0]["prompt"]
    assert "Backend Developer" in prompt
    assert "python" in prompt
    assert "hi" in prompt and "hello" in prompt
    assert "what are my skills?" in prompt


def test_json_is_requested_from_the_model(monkeypatch):
    calls = _stub_gemini(monkeypatch, _reply())

    respond("hello", PROFILE)

    assert calls[0]["response_mime_type"] == "application/json"


def test_profile_edit_is_returned(monkeypatch):
    edited = dict(PROFILE, education="Cairo University")
    _stub_gemini(
        monkeypatch,
        _reply(intent="edit_profile", updated_profile=edited,
               reply="Updated your university."),
    )

    result = respond("my university is Cairo University", PROFILE)

    assert result["intent"] == "edit_profile"
    assert result["updated_profile"]["education"] == "Cairo University"


def test_run_pipeline_flag_is_honoured(monkeypatch):
    _stub_gemini(
        monkeypatch,
        _reply(intent="confirm_run_pipeline", run_pipeline=True, reply="On it."),
    )

    assert respond("go ahead", PROFILE)["run_pipeline"] is True


def test_confirm_intent_implies_running_even_without_the_flag(monkeypatch):
    """Models set one and forget the other; either must be enough."""
    _stub_gemini(
        monkeypatch,
        _reply(intent="confirm_run_pipeline", run_pipeline=False),
    )

    assert respond("yes please", PROFILE)["run_pipeline"] is True


def test_markdown_fenced_json_is_parsed(monkeypatch):
    _stub_gemini(monkeypatch, f"```json\n{_reply(reply='Fenced.')}\n```")

    assert respond("hi", PROFILE)["reply"] == "Fenced."


# --- degradation -------------------------------------------------------------


def test_no_response_degrades_instead_of_raising(monkeypatch):
    """An unconfigured or unreachable model must not take the chat down."""
    _stub_gemini(monkeypatch, None)

    result = respond("find me matching jobs", PROFILE)

    # The one action that matters still routes correctly, and the profile is
    # handed back untouched.
    assert result["run_pipeline"] is True
    assert result["updated_profile"] == PROFILE
    assert result["reply"]


def test_unparseable_response_degrades(monkeypatch):
    _stub_gemini(monkeypatch, "I am not JSON at all")

    result = respond("find matches", PROFILE)

    assert result["run_pipeline"] is True
    assert result["updated_profile"] == PROFILE


def test_degraded_path_still_answers_offtopic_messages(monkeypatch):
    _stub_gemini(monkeypatch, None)

    result = respond("what is the weather", PROFILE)

    assert result["run_pipeline"] is False
    assert result["reply"]


def test_empty_updated_profile_does_not_wipe_the_real_one(monkeypatch):
    """A degraded answer must not destroy corrections the user typed by hand."""
    _stub_gemini(monkeypatch, _reply(updated_profile={}))

    assert respond("hi", PROFILE)["updated_profile"] == PROFILE


def test_unknown_intent_is_normalised(monkeypatch):
    _stub_gemini(monkeypatch, _reply(intent="launch_the_missiles"))

    assert respond("hi", PROFILE)["intent"] == "other"


def test_empty_message_asks_rather_than_calling_the_model(monkeypatch):
    calls = _stub_gemini(monkeypatch, _reply())

    result = respond("   ", PROFILE)

    assert result["intent"] == "clarify"
    assert calls == []


# --- the HTTP surface --------------------------------------------------------


@pytest.fixture
def client():
    from backend.routes.conversation import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_endpoint_serves_the_chat_contract(client, monkeypatch):
    """Same four keys as the CV lane's /chat, so the UI can prefer either."""
    _stub_gemini(monkeypatch, _reply(reply="Hi there."))

    body = client.post(
        "/conversation", json={"message": "hello", "profile": PROFILE}
    ).json()

    assert set(body) == {"intent", "reply", "updated_profile", "run_pipeline"}
    assert body["reply"] == "Hi there."


def test_endpoint_accepts_history(client, monkeypatch):
    calls = _stub_gemini(monkeypatch, _reply())

    response = client.post(
        "/conversation",
        json={
            "message": "and my education?",
            "profile": PROFILE,
            "history": [{"role": "user", "content": "what are my skills"}],
        },
    )

    assert response.status_code == 200
    assert "what are my skills" in calls[0]["prompt"]


def test_endpoint_does_not_500_when_the_model_is_down(client, monkeypatch):
    """The chat staying up matters more than the model being available."""
    _stub_gemini(monkeypatch, None)

    response = client.post(
        "/conversation", json={"message": "find matches", "profile": PROFILE}
    )

    assert response.status_code == 200
    assert response.json()["run_pipeline"] is True
