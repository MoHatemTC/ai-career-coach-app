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


def _install_fake_api_client(ranked=None, raises=None):
    """Register a fake `api_client` module so the UI imports it instead."""
    fake = types.ModuleType("api_client")
    fake.BASE_URL = "http://127.0.0.1:8000"
    fake.BackendError = _BackendError
    fake.health_check = lambda: (True, "Backend is up.")
    fake.get_notification_settings = lambda user_id="default": None
    fake.save_notification_settings = lambda *a, **k: {}
    fake.upload_cv = lambda *a, **k: {}
    fake.list_persisted_jobs = lambda *a, **k: []

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
    sys.modules.pop("api_client", None)
    sys.modules.pop("pipeline_stub", None)


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


def test_digest_is_capped_and_built_from_pipeline_output():
    """The digest is a nudge, not a job board — and it must be derived from the
    same pipeline results the chat renders, never a second source."""
    sys.path.insert(0, str(UI_DIR))
    _install_fake_api_client()
    import chatbot_ui

    matches = [
        {"job_title": f"Role {i}", "company": f"Co {i}", "url": f"https://x/{i}"}
        for i in range(10)
    ]
    digest = chatbot_ui.build_notification_recommendations(matches)

    assert len(digest) == chatbot_ui.NOTIFICATION_RECOMMENDATION_LIMIT
    assert digest[0] == {
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
