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

    def __init__(self, content="ok", error=None, reject_response_format=False,
                 finish_reason="stop"):
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
                choice = type(
                    "C", (),
                    {"message": message, "finish_reason": finish_reason},
                )()
                return type("R", (), {"choices": [choice]})()

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
            "openai.OpenAI", lambda **kwargs: fake
        )
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
    from backend.services import llm_client

    monkeypatch.delenv("DEFAULT_MODEL", raising=False)

    assert litellm_model() == llm_client.DEFAULT_LITELLM_MODEL


def test_a_timeout_does_not_run_the_whole_loop_twice(monkeypatch, gateway):
    """Dropping response_format on ANY error meant one unreachable gateway cost
    four requests and four timeouts before returning."""
    fake = _FakeOpenAI(error=RuntimeError("Request timed out."))
    gateway(fake)

    assert complete("hi", response_mime_type="application/json") is None
    assert len(fake.calls) == 2


def test_response_format_is_only_dropped_for_a_response_format_error(
    monkeypatch, gateway
):
    fake = _FakeOpenAI(error=RuntimeError("Request timed out."))
    gateway(fake)

    complete("hi", response_mime_type="application/json")

    # Both attempts kept it: the failure was never about JSON mode.
    assert all("response_format" in call for call in fake.calls)


def test_an_explicit_timeout_is_configured(monkeypatch):
    """The SDK default is minutes, so a wrong base URL hung instead of failing
    usefully."""
    from backend.services import llm_client

    assert 0 < llm_client.DEFAULT_TIMEOUT_SECONDS <= 120


def test_sdk_retries_are_disabled(monkeypatch, gateway):
    """Retries live here, with our own conditions; the SDK retrying underneath
    would multiply every attempt."""
    captured = {}
    fake = _FakeOpenAI()
    monkeypatch.setenv("AI_PROVIDER", "litellm")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://gateway.example/litellm")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")

    def _factory(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("openai.OpenAI", _factory)

    complete("hi")

    assert captured["max_retries"] == 0
    assert captured["timeout"] > 0


# --- base URL normalisation --------------------------------------------------


def test_v1_is_appended_when_missing():
    """The gateway advertises its base as .../litellm but serves
    .../litellm/v1/chat/completions. The SDK appends only /chat/completions, so
    pasting the advertised URL sends requests to a path that never answers and
    the call hangs until it times out."""
    from backend.services.llm_client import normalise_base_url

    assert normalise_base_url("https://learner-os.sprints.ai/litellm") == (
        "https://learner-os.sprints.ai/litellm/v1"
    )


def test_existing_version_segment_is_respected():
    from backend.services.llm_client import normalise_base_url

    assert normalise_base_url("https://x/litellm/v1") == "https://x/litellm/v1"
    assert normalise_base_url("https://x/litellm/v2") == "https://x/litellm/v2"


def test_trailing_slash_does_not_double_up():
    from backend.services.llm_client import normalise_base_url

    assert normalise_base_url("https://x/litellm/") == "https://x/litellm/v1"
    assert normalise_base_url("https://x/litellm/v1/") == "https://x/litellm/v1"


def test_empty_base_url_stays_empty():
    from backend.services.llm_client import normalise_base_url

    assert normalise_base_url("") == ""


# --- failure reasons ---------------------------------------------------------


def test_the_gateways_own_error_reaches_the_caller(monkeypatch, gateway):
    """A team key restricted to one provider answers 403 naming the model. That
    sentence is the whole diagnosis, and it used to be discarded: the caller saw
    only None and blamed the URL and the key, both of which were correct."""
    from backend.services.llm_client import complete_with_reason

    denied = RuntimeError(
        "team not allowed to access model. This team can only access "
        "models=['gemini/*']. Tried to access kimi-k2.5"
    )
    gateway(_FakeOpenAI(error=denied))

    text, reason = complete_with_reason("hi")

    assert text is None
    assert "gemini/*" in reason
    assert "kimi-k2.5" in reason


def test_the_reason_names_the_model_that_was_tried(monkeypatch, gateway):
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI(error=RuntimeError("nope")))

    _, reason = complete_with_reason("hi", model="some-model")

    assert "some-model" in reason


def test_a_missing_key_says_which_variable(monkeypatch, gateway):
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI())
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    _, reason = complete_with_reason("hi")

    assert "LITELLM_API_KEY" in reason


def test_a_missing_base_url_says_which_variable(monkeypatch, gateway):
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI())
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)

    _, reason = complete_with_reason("hi")

    assert "LITELLM_BASE_URL" in reason


def test_success_reports_no_reason(monkeypatch, gateway):
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI(content="fine"))

    assert complete_with_reason("hi") == ("fine", None)


def test_complete_still_returns_a_bare_string(monkeypatch, gateway):
    """Most callers want the text and nothing else; that surface is unchanged."""
    gateway(_FakeOpenAI(content="fine"))

    assert complete("hi") == "fine"


def test_truncated_json_is_reported_rather_than_returned(monkeypatch, gateway):
    """A JSON reply that stopped at the ceiling is unparseable. Returning it
    pushed the failure into the caller's json.loads, which reported a character
    offset and nothing about the cause: CV upload died on "Unterminated string
    starting at line 6 column 9"."""
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI(content='{"name": "Om', finish_reason="length"))

    text, reason = complete_with_reason(
        "hi", response_mime_type="application/json"
    )

    assert text is None
    assert "ceiling" in reason
    assert "LLM_MAX_TOKENS" in reason


def test_truncation_is_logged_for_callers_that_drop_the_reason(
    monkeypatch, gateway, caplog
):
    """Most services reach this through call_gemini, which returns bare text.
    Without a log line a truncated reply is an unexplained None."""
    gateway(_FakeOpenAI(content='{"a": 1', finish_reason="length"))

    with caplog.at_level("WARNING"):
        assert complete("hi", response_mime_type="application/json") is None

    assert "ceiling" in caplog.text


def test_truncated_prose_is_still_returned(monkeypatch, gateway):
    """A clipped sentence is usable; failing a chat turn over one would be the
    worse trade. Only JSON is strict about it."""
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI(content="I was saying some", finish_reason="length"))

    text, reason = complete_with_reason("hi")

    assert text == "I was saying some"
    assert reason is None


def test_a_normal_finish_is_not_treated_as_truncation(monkeypatch, gateway):
    from backend.services.llm_client import complete_with_reason

    gateway(_FakeOpenAI(content='{"name": "Omar"}', finish_reason="stop"))

    text, reason = complete_with_reason(
        "hi", response_mime_type="application/json"
    )

    assert text == '{"name": "Omar"}'
    assert reason is None


def test_the_token_ceiling_leaves_room_for_reasoning():
    """The gemini/* models bill reasoning against max_completion_tokens, so a
    ceiling sized for the answer alone gets spent before the answer starts."""
    from backend.services import llm_client

    assert llm_client.DEFAULT_MAX_TOKENS >= 4000


def test_the_token_ceiling_is_overridable(monkeypatch):
    import importlib

    from backend.services import llm_client

    monkeypatch.setenv("LLM_MAX_TOKENS", "12345")
    importlib.reload(llm_client)
    try:
        assert llm_client.DEFAULT_MAX_TOKENS == 12345
    finally:
        monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
        importlib.reload(llm_client)


def test_the_default_model_is_one_the_team_key_can_call():
    """kimi-k2.5 is what the group email advertises and what the gateway
    refuses: the grant is models=['gemini/*'], prefix included."""
    from backend.services import llm_client

    assert llm_client.DEFAULT_LITELLM_MODEL.startswith("gemini/")
    assert llm_client.DEFAULT_LITELLM_MODEL != "kimi-k2.5"


def test_the_client_is_built_with_the_normalised_url(monkeypatch):
    captured = {}
    fake = _FakeOpenAI()
    monkeypatch.setenv("AI_PROVIDER", "litellm")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://learner-os.sprints.ai/litellm")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")

    def _factory(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("openai.OpenAI", _factory)

    complete("hi")

    assert captured["base_url"] == "https://learner-os.sprints.ai/litellm/v1"
