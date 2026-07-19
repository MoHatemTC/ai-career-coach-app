"""Tests for backend/services/gemini_matcher.py.

Covers:
- SemanticMatchResult schema validation (the Pydantic contract).
- parse_and_validate: JSON parsing, code-fence stripping, and graceful
  fallback to `empty_result()` for malformed/incomplete responses.
- gemini_semantic_match: fallback behavior when GEMINI_API_KEY is
  missing, and when a network/SDK error occurs (mocked - no real
  network calls are made in this test module).

These tests never call the real Gemini API.
"""

from __future__ import annotations

import json
import types
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.services.gemini_matcher import (
    SemanticMatchResult,
    empty_result,
    gemini_semantic_match,
    parse_and_validate,
)


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
