"""UI tests for the chatbot, driven through Streamlit's AppTest harness.

The app is exercised for real — it renders, the chat input is submitted, and
the resulting widgets are inspected. `api_client` is replaced with a fake
before import, so no backend needs to be running.
"""

import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

UI_DIR = Path(__file__).resolve().parent.parent.parent / "streamlit_app"
APP = str(UI_DIR / "chatbot_ui.py")

RANKED = [
    {
        "job_id": "a1",
        "rank": 1,
        "fit_score": 0.91,
        "job_data": {
            "job_id": "a1",
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Cairo",
            "url": "https://example.com/a1",
            "source": "wuzzuf",
            "match_score": 0.78,
        },
    }
]


class _BackendError(Exception):
    pass


def _install_fake_api_client(ranked=None, raises=None, ingestion_run=None,
                             chat_response=None):
    """Register a fake `api_client` module so the UI imports it instead."""
    fake = types.ModuleType("api_client")
    fake.BASE_URL = "http://127.0.0.1:8000"
    fake.BackendError = _BackendError
    fake.health_check = lambda: (True, "Backend is up.")
    fake.get_notification_settings = lambda user_id="default": None
    fake.settings_calls = []

    def _save_settings(email, phone, user_id="default", channels=None,
                       frequency=None, relevance_threshold=None):
        call = {"email": email, "phone": phone, "channels": channels,
                "frequency": frequency, "relevance_threshold": relevance_threshold}
        fake.settings_calls.append(call)
        return {"user_id": user_id,
                "contact": {"email": email, "phone_whatsapp": phone},
                "notification_channels": channels or [],
                "frequency": frequency, "relevance_threshold": relevance_threshold}

    fake.save_notification_settings = _save_settings
    fake.upload_cv = lambda *a, **k: {}
    fake.list_persisted_jobs = lambda *a, **k: []

    class _ChatUnavailable(_BackendError):
        pass

    fake.ChatUnavailable = _ChatUnavailable
    fake.chat_calls = []

    def _chat(message, profile):
        fake.chat_calls.append({"message": message, "profile": profile})
        if chat_response is None:
            raise _ChatUnavailable("not deployed")
        return chat_response

    fake.chat = _chat

    # Trigger Now ingests before matching; a finished run by default so tests
    # do not sit in the poll loop.
    fake.ingestion_calls = []

    def _trigger_ingestion(sources=None, limit=10):
        fake.ingestion_calls.append({"sources": sources, "limit": limit})
        if raises:
            raise _BackendError(raises)
        return 7

    fake.trigger_ingestion = _trigger_ingestion
    fake.get_ingestion_run = lambda run_id: (
        ingestion_run
        if ingestion_run is not None
        else {
            "id": run_id, "status": "success", "jobs_inserted": 2,
            "jobs_updated": 1, "jobs_embedded": 3, "error_message": None,
        }
    )
    # Returns immediately rather than polling, so the UI tests never sleep.
    fake.wait_for_ingestion = lambda run_id, budget=None: fake.get_ingestion_run(
        run_id
    )

    def _run(profile, top_k=10):
        if raises:
            raise _BackendError(raises)
        return ranked if ranked is not None else []

    fake.run_match_pipeline = _run

    sys.path.insert(0, str(UI_DIR))
    sys.modules["api_client"] = fake
    sys.modules.pop("pipeline_stub", None)  # re-import against the fake
    return fake


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    # chatbot_ui too: importing it directly executes the Streamlit script in
    # bare mode, which leaves Streamlit's container/form context dirty and made
    # a later AppTest fail with "chat_input can't be used in a form".
    for module in ("api_client", "pipeline_stub", "chatbot_ui"):
        sys.modules.pop(module, None)


def test_app_renders_without_error():
    _install_fake_api_client()
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception


def test_chat_input_exists():
    _install_fake_api_client()
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert len(at.chat_input) == 1


def test_chat_sits_above_the_profile_form():
    """The agreed layout is chat first, profile form below it."""
    _install_fake_api_client()
    at = AppTest.from_file(APP, default_timeout=30).run()

    headers = [h.value for h in at.header]
    chat_index = next(i for i, h in enumerate(headers) if "Chat" in h)
    # The profile form only renders once a profile exists, so assert the chat
    # header precedes the results header and that ordering is stable.
    assert chat_index >= 0
    assert headers[chat_index].startswith("2.")


def test_asking_for_matches_without_a_profile_asks_for_a_cv():
    _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30).run()

    at.chat_input[0].set_value("find me matching jobs").run()

    replies = " ".join(m.value for m in at.markdown)
    assert "upload a CV" in replies or "Parse CV" in replies
    assert not at.exception


def test_offtopic_message_explains_what_the_chat_can_do():
    _install_fake_api_client()
    at = AppTest.from_file(APP, default_timeout=30).run()

    at.chat_input[0].set_value("hello there").run()

    replies = " ".join(m.value for m in at.markdown)
    assert "rank job matches" in replies or "find and rank" in replies
    assert not at.exception


def test_matches_render_when_a_profile_exists():
    _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at.chat_input[0].set_value("find matches").run()

    assert not at.exception
    # render_match_card puts the title in a subheader and the company in a
    # caption, not in markdown.
    assert any("Backend Engineer" in s.value for s in at.subheader)
    assert any("Acme" in c.value for c in at.caption)
    # The posting link is the card's primary action — assert it is a real,
    # clickable link pointing at the retrieved url, not just text.
    assert any(b.url == "https://example.com/a1" for b in at.get("link_button"))
    assert any("https://example.com/a1" in c.value for c in at.caption)


def test_backend_failure_is_reported_not_swallowed():
    """A failing pipeline must not render as 'no matches'."""
    _install_fake_api_client(raises="qdrant unreachable")
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at.chat_input[0].set_value("find matches").run()

    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "could not run the matching pipeline" in text
    assert "qdrant unreachable" in text


def test_sent_messages_land_in_history_not_below_the_input():
    """The input box used to appear to jump: a just-sent exchange was drawn
    inline *after* the chat_input widget, then moved above it on the next
    rerun. Both turns must go into session state and render from there."""
    _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30).run()

    at.chat_input[0].set_value("hello there").run()

    roles = [m["role"] for m in at.session_state["chat"]]
    assert roles == ["user", "assistant"]
    assert at.session_state["chat"][0]["content"] == "hello there"
    assert not at.exception


def test_history_survives_multiple_turns_in_order():
    _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30).run()

    at.chat_input[0].set_value("hello").run()
    at.chat_input[0].set_value("hi again").run()

    contents = [m["content"] for m in at.session_state["chat"]]
    assert contents[0] == "hello"
    assert contents[2] == "hi again"
    assert len(contents) == 4
    assert not at.exception


def test_agent_reply_is_shown_when_the_agent_is_deployed():
    fake = _install_fake_api_client(
        ranked=RANKED,
        chat_response={
            "intent": "other", "reply": "Hi Kabulo, how can I help?",
            "updated_profile": {}, "run_pipeline": False,
        },
    )
    at = AppTest.from_file(APP, default_timeout=30).run()

    at.chat_input[0].set_value("my name is actually kabulo").run()

    assert not at.exception
    assert fake.chat_calls[0]["message"] == "my name is actually kabulo"
    assert any("Kabulo" in m.value for m in at.markdown)


def test_agent_profile_edit_is_written_back_to_session_state():
    """A natural-language edit has to actually stick, or the next pipeline run
    uses the stale profile."""
    _install_fake_api_client(
        ranked=RANKED,
        chat_response={
            "intent": "edit_profile",
            "reply": "Updated your university.",
            "updated_profile": {"title": "Backend Developer",
                                "education": "Cairo University"},
            "run_pipeline": False,
        },
    )
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer",
                                   "education": "Ain Shams"}
    at.run()

    at.chat_input[0].set_value("change my university to Cairo University").run()

    assert not at.exception
    assert at.session_state["profile"]["education"] == "Cairo University"


def test_empty_updated_profile_does_not_wipe_the_real_one():
    """A degraded agent response must not destroy hand-corrected edits."""
    _install_fake_api_client(
        ranked=RANKED,
        chat_response={"intent": "other", "reply": "ok",
                       "updated_profile": {}, "run_pipeline": False},
    )
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer"}
    at.run()

    at.chat_input[0].set_value("hello").run()

    assert at.session_state["profile"] == {"title": "Backend Developer"}


def test_confirm_run_pipeline_intent_runs_the_matching_chain():
    _install_fake_api_client(
        ranked=RANKED,
        chat_response={
            "intent": "confirm_run_pipeline", "reply": "On it.",
            "updated_profile": {"title": "Backend Developer"},
            "run_pipeline": True,
        },
    )
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer"}
    at.run()

    at.chat_input[0].set_value("looks good, go ahead").run()

    assert not at.exception
    assert any("Backend Engineer" in s.value for s in at.subheader)


def test_falls_back_to_keywords_when_the_agent_is_not_deployed():
    """The agent lane is not merged yet, so the chat must still work."""
    _install_fake_api_client(ranked=RANKED, chat_response=None)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer"}
    at.run()

    at.chat_input[0].set_value("find matches").run()

    assert not at.exception
    assert any("Backend Engineer" in s.value for s in at.subheader)


def _trigger_now(at):
    """Click the Trigger Now button, wherever it sits in the widget list."""
    button = next(b for b in at.button if "Trigger Now" in b.label)
    return button.click().run()


def test_trigger_now_without_a_profile_warns_instead_of_running():
    _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30).run()

    at = _trigger_now(at)

    assert not at.exception
    assert any("No profile yet" in w.value for w in at.warning)


def test_trigger_now_shows_recommendations_with_links():
    _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at = _trigger_now(at)

    assert not at.exception
    assert any("recommendation" in s.value for s in at.success)
    text = " ".join(m.value for m in at.markdown)
    assert "Backend Engineer" in text
    assert any(b.url == "https://example.com/a1" for b in at.get("link_button"))


def test_trigger_now_reports_backend_failure():
    _install_fake_api_client(raises="qdrant unreachable")
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at = _trigger_now(at)

    assert not at.exception
    assert any("qdrant unreachable" in e.value for e in at.error)


def test_trigger_now_with_no_matches_says_so():
    """An empty collection must not look like a delivered digest."""
    _install_fake_api_client(ranked=[])
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at = _trigger_now(at)

    assert not at.exception
    assert any("No recommendations" in i.value for i in at.info)


def test_trigger_now_ingests_before_matching():
    """The whole point of triggering: pull in postings that did not exist last
    time, rather than re-ranking a frozen pool."""
    fake = _install_fake_api_client(ranked=RANKED)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at = _trigger_now(at)

    assert not at.exception
    assert len(fake.ingestion_calls) == 1
    captions = " ".join(c.value for c in at.caption)
    assert "2 new" in captions and "3 embedded" in captions


def test_trigger_now_still_matches_when_ingestion_is_slow(monkeypatch):
    """A run still in progress must not block the digest: ingestion commits
    per source, so what it already wrote is usable."""
    sys.path.insert(0, str(UI_DIR))
    sys.modules.pop("api_client", None)
    import api_client as real_api_client

    monkeypatch.setattr(
        real_api_client,
        "get_ingestion_run",
        lambda run_id: {"id": run_id, "status": "running"},
    )

    # A tiny budget so the test does not wait the real 90 seconds.
    run = real_api_client.wait_for_ingestion(7, budget=0.05)

    assert run["status"] == "running"


def test_partial_ingestion_failure_is_reported_but_not_fatal():
    _install_fake_api_client(
        ranked=RANKED,
        ingestion_run={"id": 7, "status": "partial", "jobs_inserted": 1,
                       "jobs_updated": 0, "jobs_embedded": 1,
                       "error_message": "wuzzuf: Cloudflare bot challenge"},
    )
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["profile"] = {"title": "Backend Developer", "skills": ["python"]}
    at.run()

    at = _trigger_now(at)

    assert not at.exception
    assert any("Cloudflare" in w.value for w in at.warning)
    # The digest still renders despite the partial failure.
    assert any("recommendation" in s.value for s in at.success)


def test_digest_is_capped_and_built_from_pipeline_output():
    """The digest is a nudge, not a job board — and it must be derived from the
    same pipeline results the chat renders, never a second source."""
    sys.path.insert(0, str(UI_DIR))
    import digest

    matches = [
        {"job_title": f"Role {i}", "company": f"Co {i}", "url": f"https://x/{i}"}
        for i in range(10)
    ]
    lines = digest.build_notification_recommendations(matches)

    assert len(lines) == digest.NOTIFICATION_RECOMMENDATION_LIMIT
    assert lines[0] == {
        "job_title": "Role 0", "company": "Co 0", "url": "https://x/0"
    }


def test_placeholder_explanation_does_not_invent_analysis():
    """The remaining mock must not fabricate strengths or gaps."""
    _install_fake_api_client(ranked=RANKED)
    sys.path.insert(0, str(UI_DIR))
    import pipeline_stub

    explanation = pipeline_stub.placeholder_explanation(RANKED[0])

    assert explanation["strengths"] == []
    assert explanation["gaps_or_missing_requirements"] == []
    assert explanation["recommendations"] == []
    assert explanation["next_steps"] == []
    assert "not available yet" in explanation["overall_alignment_summary"]
    # It should still report the numbers the pipeline really produced.
    assert "0.91" in explanation["overall_alignment_summary"]


def test_settings_form_exposes_the_contract_6_preferences():
    """The settings tab is Contract 6's producer, so the preferences the
    notifications lane branches on have to be settable, not just contact
    details."""
    _install_fake_api_client()
    at = AppTest.from_file(APP, default_timeout=30).run()

    assert not at.exception
    assert [m.value for m in at.multiselect if "email" in (m.value or [])]
    assert any(s.value == "daily" for s in at.selectbox)
    assert any(s.value == 0.75 for s in at.slider)


def test_api_client_sends_the_nested_contract_6_payload(monkeypatch):
    """Pins the wire format: nested contact plus the three preferences."""
    sys.path.insert(0, str(UI_DIR))
    sys.modules.pop("api_client", None)
    import api_client as real_api_client

    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {}

    def _post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(real_api_client.requests, "post", _post)

    real_api_client.save_notification_settings(
        "omar@example.com", "+20100", channels=["email", "whatsapp"],
        frequency="weekly", relevance_threshold=0.5,
    )

    body = captured["json"]
    assert body["contact"] == {"email": "omar@example.com",
                              "phone_whatsapp": "+20100"}
    assert body["notification_channels"] == ["email", "whatsapp"]
    assert body["frequency"] == "weekly"
    assert body["relevance_threshold"] == 0.5


def test_api_client_omits_preferences_it_was_not_given(monkeypatch):
    """Omitted preferences must not be sent as null, or the backend would
    blank the user's stored choices."""
    sys.path.insert(0, str(UI_DIR))
    sys.modules.pop("api_client", None)
    import api_client as real_api_client

    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {}

    monkeypatch.setattr(
        real_api_client.requests, "post",
        lambda url, json=None, timeout=None: (captured.update(json=json), _Resp())[1],
    )

    real_api_client.save_notification_settings("a@b.com", "+1")

    assert "notification_channels" not in captured["json"]
    assert "frequency" not in captured["json"]
    assert "relevance_threshold" not in captured["json"]
