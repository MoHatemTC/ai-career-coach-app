"""Tests for backend/services/gemini_matcher.py.

Covers:
- SemanticMatchResult schema validation (the Pydantic contract).
- parse_and_validate: JSON parsing, code-fence stripping, and graceful
  fallback to `empty_result()` for malformed/incomplete responses.
- gemini_semantic_match: fallback behavior when GEMINI_API_KEY is
  missing, and when a network/SDK error occurs (mocked - no real
  network calls are made in this test module).
- Cached prompt loading (`_load_prompt_template`).
- GEMINI_MODEL environment-variable model selection.
- Bounded retry (1 retry) on transient failures, no retry on
  non-transient ones.
- The `SemanticMatcher` / `GeminiMatcher` provider interface.

These tests never call the real Gemini API.

`call_gemini` is now a router: `AI_PROVIDER` decides whether a request goes to
the LiteLLM gateway (the default, since the direct Gemini keys are heavily rate
limited) or to Gemini itself. Everything here exercises the Gemini path
specifically -- model selection from GEMINI_MODEL, the SDK's retry behaviour --
so the autouse fixture below selects that provider explicitly rather than
depending on whatever the environment happens to say.
"""

from __future__ import annotations

import json
import types
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.services.gemini_matcher import (
    GeminiMatcher,
    SemanticMatcher,
    SemanticMatchResult,
    _is_transient_error,
    _load_prompt_template,
    empty_result,
    gemini_semantic_match,
    parse_and_validate,
)


@pytest.fixture(autouse=True)
def _use_gemini_provider(monkeypatch):
    """Route call_gemini to Gemini for this module, which is what it tests."""
    monkeypatch.setenv("AI_PROVIDER", "gemini")



# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSemanticMatchResultSchema:
    def test_accepts_a_fully_populated_valid_response(self):
        data = {
            "matched_skills": [
                {
                    "required_skill": "REST APIs",
                    "candidate_skill": "FastAPI",
                    "confidence": 0.95,
                    "reason": "FastAPI is a framework for building REST APIs.",
                }
            ],
            "partially_matched": [
                {
                    "required_skill": "Data Analysis",
                    "candidate_skill": "Pandas",
                    "confidence": 0.6,
                    "reason": "Pandas is a tool used for data analysis, not the skill itself.",
                }
            ],
            "missing_skills": [
                {"required_skill": "Kubernetes", "reason": "No related skill found."}
            ],
        }
        result = SemanticMatchResult.model_validate(data)
        assert result.matched_skills[0].candidate_skill == "FastAPI"
        assert result.partially_matched[0].confidence == 0.6
        assert result.missing_skills[0].required_skill == "Kubernetes"

    def test_defaults_to_empty_lists_when_fields_missing(self):
        result = SemanticMatchResult.model_validate({})
        assert result.matched_skills == []
        assert result.partially_matched == []
        assert result.missing_skills == []

    def test_rejects_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            SemanticMatchResult.model_validate(
                {
                    "matched_skills": [
                        {
                            "required_skill": "Docker",
                            "candidate_skill": "Docker Compose",
                            "confidence": 1.5,
                            "reason": "out of range",
                        }
                    ]
                }
            )

    def test_rejects_missing_required_field(self):
        with pytest.raises(ValidationError):
            SemanticMatchResult.model_validate(
                {"matched_skills": [{"candidate_skill": "Docker", "confidence": 0.9}]}
            )


# ---------------------------------------------------------------------------
# parse_and_validate: never raises, always falls back gracefully
# ---------------------------------------------------------------------------


class TestParseAndValidate:
    def test_parses_clean_json(self):
        payload = {
            "matched_skills": [
                {
                    "required_skill": "Git",
                    "candidate_skill": "GitHub",
                    "confidence": 0.9,
                    "reason": "GitHub is a hosting service built on Git.",
                }
            ]
        }
        result = parse_and_validate(json.dumps(payload))
        assert result.matched_skills[0].required_skill == "Git"

    def test_strips_markdown_code_fences(self):
        payload = json.dumps({"matched_skills": []})
        fenced = f"```json\n{payload}\n```"
        result = parse_and_validate(fenced)
        assert result == empty_result()

    def test_falls_back_on_invalid_json(self):
        result = parse_and_validate("not json at all {{{")
        assert result == empty_result()

    def test_falls_back_on_empty_string(self):
        assert parse_and_validate("") == empty_result()
        assert parse_and_validate("   ") == empty_result()

    def test_falls_back_on_non_object_json(self):
        assert parse_and_validate("[1, 2, 3]") == empty_result()
        assert parse_and_validate('"just a string"') == empty_result()

    def test_falls_back_on_schema_violation(self):
        # confidence out of [0, 1] range -> fails validation -> fallback,
        # never raises up to the caller.
        bad = json.dumps(
            {
                "matched_skills": [
                    {
                        "required_skill": "Docker",
                        "candidate_skill": "Docker Compose",
                        "confidence": 42,
                        "reason": "bad confidence value",
                    }
                ]
            }
        )
        assert parse_and_validate(bad) == empty_result()

    def test_falls_back_on_incomplete_entry_missing_required_field(self):
        bad = json.dumps(
            {"missing_skills": [{"reason": "no required_skill field present"}]}
        )
        assert parse_and_validate(bad) == empty_result()


# ---------------------------------------------------------------------------
# gemini_semantic_match: configuration / failure fallbacks (mocked)
# ---------------------------------------------------------------------------


def _fake_google_modules(genai_module: types.ModuleType) -> dict:
    """Build sys.modules entries so `from google import genai` resolves
    to `genai_module`, without needing the real google-genai package
    installed in the test environment."""
    fake_google = types.ModuleType("google")
    fake_google.genai = genai_module
    return {"google": fake_google, "google.genai": genai_module}


class TestGeminiSemanticMatchFallbacks:
    def test_returns_empty_result_when_no_required_skills(self):
        result = gemini_semantic_match(["Python"], [], api_key="fake-key")
        assert result == empty_result()

    def test_returns_empty_result_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = gemini_semantic_match(["Python"], ["Docker"], api_key=None)
        assert result == empty_result()

    def test_returns_empty_result_when_sdk_call_raises(self):
        class _BoomClient:
            def __init__(self, api_key):
                raise RuntimeError("network is down")

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _BoomClient

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            result = gemini_semantic_match(
                ["Python"], ["Docker"], api_key="fake-key"
            )
        assert result == empty_result()

    def test_uses_provided_response_text_end_to_end(self):
        payload = json.dumps(
            {
                "matched_skills": [
                    {
                        "required_skill": "Deep Learning",
                        "candidate_skill": "PyTorch",
                        "confidence": 0.93,
                        "reason": "PyTorch is a deep learning framework.",
                    }
                ]
            }
        )

        class _FakeResponse:
            text = payload

        class _FakeModels:
            def generate_content(self, model, contents):
                return _FakeResponse()

        class _FakeClient:
            def __init__(self, api_key):
                self.models = _FakeModels()

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _FakeClient

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            result = gemini_semantic_match(
                ["PyTorch"], ["Deep Learning"], api_key="fake-key"
            )

        assert result.matched_skills[0].candidate_skill == "PyTorch"
        assert result.matched_skills[0].confidence == 0.93


# ---------------------------------------------------------------------------
# Prompt loading is cached (read from disk once, reused after)
# ---------------------------------------------------------------------------


class TestPromptCaching:
    def test_prompt_is_read_from_disk_only_once(self):
        _load_prompt_template.cache_clear()

        mock_path = MagicMock()
        mock_path.read_text.return_value = "fake prompt body"

        with patch("backend.services.gemini_matcher._PROMPT_PATH", mock_path):
            first = _load_prompt_template()
            second = _load_prompt_template()
            third = _load_prompt_template()

        assert first == second == third == "fake prompt body"
        mock_path.read_text.assert_called_once()

        _load_prompt_template.cache_clear()

    def test_cache_clear_forces_a_fresh_read(self):
        _load_prompt_template.cache_clear()

        mock_path = MagicMock()
        mock_path.read_text.side_effect = ["first version", "second version"]

        with patch("backend.services.gemini_matcher._PROMPT_PATH", mock_path):
            first = _load_prompt_template()
            _load_prompt_template.cache_clear()
            second = _load_prompt_template()

        assert (first, second) == ("first version", "second version")
        assert mock_path.read_text.call_count == 2

        _load_prompt_template.cache_clear()


# ---------------------------------------------------------------------------
# Model selection: GEMINI_MODEL env var, with a hardcoded fallback default
# ---------------------------------------------------------------------------


class TestModelSelection:
    def _capture_model(self, monkeypatch, env_value, explicit_model=None):
        """Run gemini_semantic_match and capture the `model=` it actually
        passed to the SDK, without needing a real network call."""
        if env_value is None:
            monkeypatch.delenv("GEMINI_MODEL", raising=False)
        else:
            monkeypatch.setenv("GEMINI_MODEL", env_value)

        captured = {}

        class _FakeResponse:
            text = json.dumps({})

        class _FakeModels:
            def generate_content(self, model, contents):
                captured["model"] = model
                return _FakeResponse()

        class _FakeClient:
            def __init__(self, api_key):
                self.models = _FakeModels()

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _FakeClient

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            gemini_semantic_match(
                ["Python"], ["Docker"], model=explicit_model, api_key="fake-key"
            )

        return captured["model"]

    def test_uses_gemini_model_env_var_when_set(self, monkeypatch):
        model = self._capture_model(monkeypatch, env_value="gemini-1.5-flash")
        assert model == "gemini-1.5-flash"

    def test_falls_back_to_default_model_when_env_var_unset(self, monkeypatch):
        model = self._capture_model(monkeypatch, env_value=None)
        assert model == "gemini-2.5-pro"

    def test_explicit_model_argument_wins_over_env_var(self, monkeypatch):
        model = self._capture_model(
            monkeypatch, env_value="gemini-1.5-flash", explicit_model="gemini-2.0-ultra"
        )
        assert model == "gemini-2.0-ultra"


# ---------------------------------------------------------------------------
# Transient-failure retry: exactly one retry, never unbounded
# ---------------------------------------------------------------------------


class TestTransientRetry:
    def test_is_transient_error_detects_status_code(self):
        class _RateLimited(Exception):
            status_code = 429

        assert _is_transient_error(_RateLimited("nope")) is True

    def test_is_transient_error_detects_message_markers(self):
        assert _is_transient_error(Exception("Connection timed out")) is True
        assert _is_transient_error(Exception("service unavailable")) is True

    def test_is_transient_error_false_for_non_transient(self):
        assert _is_transient_error(Exception("invalid API key")) is False

    def test_retries_once_on_transient_error_then_succeeds(self):
        payload = json.dumps(
            {
                "matched_skills": [
                    {
                        "required_skill": "Docker",
                        "candidate_skill": "Docker Compose",
                        "confidence": 0.9,
                        "reason": "close enough",
                    }
                ]
            }
        )

        class _FakeResponse:
            text = payload

        call_count = {"n": 0}

        class _FlakyModels:
            def generate_content(self, model, contents):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise TimeoutError("Connection timed out")
                return _FakeResponse()

        class _FakeClient:
            def __init__(self, api_key):
                self.models = _FlakyModels()

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _FakeClient

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            result = gemini_semantic_match(["Docker"], ["Docker"], api_key="fake-key")

        assert call_count["n"] == 2
        assert result.matched_skills[0].candidate_skill == "Docker Compose"

    def test_does_not_retry_more_than_once(self):
        call_count = {"n": 0}

        class _AlwaysFlakyModels:
            def generate_content(self, model, contents):
                call_count["n"] += 1
                raise TimeoutError("Connection timed out")

        class _FakeClient:
            def __init__(self, api_key):
                self.models = _AlwaysFlakyModels()

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _FakeClient

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            result = gemini_semantic_match(["Docker"], ["Docker"], api_key="fake-key")

        # 2 attempts total: 1 original call + exactly 1 retry, never more.
        assert call_count["n"] == 2
        assert result == empty_result()

    def test_does_not_retry_non_transient_errors(self):
        call_count = {"n": 0}

        class _AuthFailModels:
            def generate_content(self, model, contents):
                call_count["n"] += 1
                raise PermissionError("invalid API key")

        class _FakeClient:
            def __init__(self, api_key):
                self.models = _AuthFailModels()

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _FakeClient

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            result = gemini_semantic_match(["Docker"], ["Docker"], api_key="fake-key")

        # Non-transient failure -> fall back immediately, no retry.
        assert call_count["n"] == 1
        assert result == empty_result()


# ---------------------------------------------------------------------------
# Provider interface: skill_gap.py depends only on SemanticMatcher
# ---------------------------------------------------------------------------


class TestSemanticMatcherInterface:
    def test_semantic_matcher_cannot_be_instantiated_directly(self):
        # It's an abstract interface, not a usable class on its own -
        # every provider (Gemini, and future ones) must subclass it.
        with pytest.raises(TypeError):
            SemanticMatcher()  # type: ignore[abstract]

    def test_gemini_matcher_implements_semantic_matcher(self):
        matcher = GeminiMatcher()
        assert isinstance(matcher, SemanticMatcher)
        assert hasattr(matcher, "match")

    def test_gemini_matcher_match_falls_back_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        matcher = GeminiMatcher()
        result = matcher.match(["Python"], ["Docker"])
        assert result == empty_result()

    def test_gemini_matcher_honors_explicit_model_and_key(self):
        captured = {}

        class _FakeResponse:
            text = json.dumps({})

        class _FakeModels:
            def generate_content(self, model, contents):
                captured["model"] = model
                return _FakeResponse()

        class _FakeClient:
            def __init__(self, api_key):
                captured["api_key"] = api_key
                self.models = _FakeModels()

        fake_genai_module = types.ModuleType("google.genai")
        fake_genai_module.Client = _FakeClient

        matcher = GeminiMatcher(model="gemini-custom", api_key="explicit-key")

        with patch.dict("sys.modules", _fake_google_modules(fake_genai_module)):
            matcher.match(["Python"], ["Docker"])

        assert captured["model"] == "gemini-custom"
        assert captured["api_key"] == "explicit-key"

    def test_a_second_provider_can_implement_the_same_interface(self):
        # Demonstrates the whole point of the interface: a brand new
        # provider (e.g. a future OpenAIMatcher) just needs to subclass
        # SemanticMatcher - skill_gap.py never needs to change.
        class StubOtherProviderMatcher(SemanticMatcher):
            def match(self, candidate_skills, required_skills) -> SemanticMatchResult:
                return empty_result()

        other_provider = StubOtherProviderMatcher()
        assert isinstance(other_provider, SemanticMatcher)
        assert other_provider.match(["Python"], ["Docker"]) == empty_result()
