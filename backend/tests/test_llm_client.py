"""Tests for the provider switch.

The gateway is never actually called: the OpenAI SDK's client is substituted.
What matters is that the switch routes correctly, sends the right request, and
degrades to None instead of raising, since every caller relies on that contract
to fall back to something deterministic.
"""

import pytest

from backend.services import llm_client
from backend.services.llm_client import active_provider, complete, litellm_model


class _FakeOpenAI:
    """Records the request and returns a fixed completion."""

    def __init__(self, content="ok", error=None, reject_response_format=False):
        self.calls = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                if reject_response_format and "response_format" in kwargs:
                    raise RuntimeError("response_format is not supported")
                if error is not None:
                    raise error
                message = type("M", (), {"content": content})()
                return type("R", (), {"choices": [type("C", (), {"message": message})()]})()

        self.chat = type("Chat", (), {"completions": _Completions()})()


@pytest.fixture
def gateway(monkeypatch):
    """Point the client at a fake gateway with credentials present."""
    monkeypatch.setenv("AI_PROVIDER", "litellm")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://gateway.example/litellm")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("DEFAULT_MODEL", "kimi-k2.5")

    holder = {}

    def _install(fake):
        holder["fake"] = fake
        monkeypatch.setattr(
            "openai.OpenAI", lambda base_url=None, api_key=None: fake
        )
        holder["base_url"] = base_url_capture = {}
        return fake

    return _install


# --- routing -----------------------------------------------------------------


def test_litellm_is_the_default(monkeypatch):
    """Gemini direct is rate limited; the gateway is the sane default."""
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    assert active_provider() == "litellm"


def test_provider_is_read_at_call_time(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert active_provider() == "gemini"
    monkeypatch.setenv("AI_PROVIDER", "litellm")
    assert active_provider() == "litellm"


def test_gemini_provider_delegates_to_the_direct_call(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    captured = {}

    def _direct(prompt, **kwargs):
        captured["prompt"] = prompt
        return "from gemini"

    monkeypatch.setattr(
        "backend.services.gemini_client.call_gemini_direct", _direct
    )

    assert complete("hello") == "from gemini"
    assert captured["prompt"] == "hello"


def test_unknown_provider_falls_back_to_litellm(monkeypatch, gateway):
    fake = _FakeOpenAI(content="fallback")
    gateway(fake)
    monkeypatch.setenv("AI_PROVIDER", "something-else")

    assert complete("hi") == "fallback"


# --- the request -------------------------------------------------------------


def test_model_comes_from_default_model(monkeypatch, gateway):
    fake = _FakeOpenAI()
    gateway(fake)

    complete("hi")

    assert fake.calls[0]["model"] == "kimi-k2.5"


def test_explicit_model_wins(monkeypatch, gateway):
    fake = _FakeOpenAI()
    gateway(fake)

    complete("hi", model="other-model")

    assert fake.calls[0]["model"] == "other-model"


def test_prompt_is_sent_as_a_user_message(monkeypatch, gateway):
    fake = _FakeOpenAI()
    gateway(fake)

    complete("summarise this CV")

    messages = fake.calls[0]["messages"]
    assert messages == [{"role": "user", "content": "summarise this CV"}]


def test_max_completion_tokens_is_always_sent(monkeypatch, gateway):
    """The gateway's own examples set it, and some models reject an unbounded
    completion."""
    fake = _FakeOpenAI()
    gateway(fake)

    complete("hi")

    assert fake.calls[0]["max_completion_tokens"] > 0


def test_temperature_is_only_sent_when_given(monkeypatch, gateway):
    fake = _FakeOpenAI()
    gateway(fake)

    complete("hi")
    assert "temperature" not in fake.calls[0]

    complete("hi", temperature=0.0)
    assert fake.calls[1]["temperature"] == 0.0


def test_json_mode_is_requested_when_asked_for(monkeypatch, gateway):
    fake = _FakeOpenAI()
    gateway(fake)

    complete("hi", response_mime_type="application/json")

    assert fake.calls[0]["response_format"] == {"type": "json_object"}


def test_unsupported_json_mode_retries_without_it(monkeypatch, gateway):
    """Not every model behind the gateway supports response_format. Failing the
    call over it would be worse than parsing defensively, which callers already
    do."""
    fake = _FakeOpenAI(content="plain", reject_response_format=True)
    gateway(fake)

    result = complete("hi", response_mime_type="application/json")

    assert result == "plain"
    assert "response_format" in fake.calls[0]
    assert "response_format" not in fake.calls[-1]


# --- degradation -------------------------------------------------------------


def test_missing_key_returns_none(monkeypatch, gateway):
    gateway(_FakeOpenAI())
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    assert complete("hi") is None


def test_missing_base_url_returns_none(monkeypatch, gateway):
    gateway(_FakeOpenAI())
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)

    assert complete("hi") is None


def test_provider_error_returns_none_rather_than_raising(monkeypatch, gateway):
    """Every caller depends on this to fall back deterministically."""
    gateway(_FakeOpenAI(error=RuntimeError("gateway exploded")))

    assert complete("hi") is None


def test_transient_error_is_retried_once(monkeypatch, gateway):
    fake = _FakeOpenAI(error=RuntimeError("429 rate limit exceeded"))
    gateway(fake)

    assert complete("hi") is None
    assert len(fake.calls) == 2


def test_non_transient_error_is_not_retried(monkeypatch, gateway):
    """Bad auth fails identically the second time; retrying only adds latency."""
    fake = _FakeOpenAI(error=RuntimeError("401 invalid api key"))
    gateway(fake)

    assert complete("hi") is None
    assert len(fake.calls) == 1


def test_default_model_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)

    assert litellm_model() == "kimi-k2.5"
