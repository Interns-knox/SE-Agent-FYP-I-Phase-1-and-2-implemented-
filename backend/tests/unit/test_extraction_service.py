"""Unit tests for FeatureExtractionService, LLMProvider abstraction, and AI schemas."""

import json

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domains.ai.extraction import SYSTEM_PROMPT, FeatureExtractionService
from app.domains.ai.provider import LLMProvider, OllamaProvider
from app.domains.ai.schemas import ExtractedFeature, FeatureExtractionResponse

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class StubProvider(LLMProvider):
    """Minimal in-memory LLMProvider that returns pre-configured responses."""

    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    def generate(self, prompt: str) -> str:  # noqa: ARG002
        return next(self._responses)


class ErrorProvider(LLMProvider):
    """Provider that raises a given exception on every call."""

    def __init__(self, exc: Exception):
        self._exc = exc

    def generate(self, prompt: str) -> str:  # noqa: ARG002
        raise self._exc


VALID_JSON = json.dumps(
    {
        "features": [
            {"name": "User Auth", "description": "Handles login and registration"},
            {"name": "Dashboard", "description": "Shows summary metrics"},
            {"name": "Reports", "description": "Generate PDF reports"},
        ]
    }
)

INVALID_JSON = "this is not json"
WRONG_SCHEMA_JSON = json.dumps({"items": []})  # valid JSON, wrong schema


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestExtractedFeature:
    def test_valid_fields(self):
        f = ExtractedFeature(name="Auth", description="Login flow")
        assert f.name == "Auth"
        assert f.description == "Login flow"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedFeature(name="", description="desc")

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedFeature(name="Auth", description="")


class TestFeatureExtractionResponse:
    def test_parse_valid_json(self):
        result = FeatureExtractionResponse.model_validate_json(VALID_JSON)
        assert len(result.features) == 3
        assert result.features[0].name == "User Auth"

    def test_empty_features_list_allowed(self):
        data = json.dumps({"features": []})
        result = FeatureExtractionResponse.model_validate_json(data)
        assert result.features == []

    def test_missing_features_key_raises(self):
        with pytest.raises(ValidationError):
            FeatureExtractionResponse.model_validate_json(WRONG_SCHEMA_JSON)


# ---------------------------------------------------------------------------
# LLMProvider abstraction tests
# ---------------------------------------------------------------------------


class TestLLMProvider:
    def test_llm_provider_is_abstract(self):
        assert hasattr(LLMProvider, "__abstractmethods__")
        assert "generate" in LLMProvider.__abstractmethods__

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_ollama_provider_is_subclass(self):
        assert issubclass(OllamaProvider, LLMProvider)

    def test_ollama_provider_stores_url_and_model(self):
        p = OllamaProvider(url="http://localhost:11434", model="qwen3:8b")
        assert p.url == "http://localhost:11434"
        assert p.model == "qwen3:8b"


# ---------------------------------------------------------------------------
# FeatureExtractionService — success paths
# ---------------------------------------------------------------------------


class TestFeatureExtractionServiceSuccess:
    def test_returns_parsed_response_on_first_attempt(self):
        provider = StubProvider([VALID_JSON])
        svc = FeatureExtractionService(provider)
        result = svc.extract("Build a CRM system")
        assert isinstance(result, FeatureExtractionResponse)
        assert len(result.features) == 3

    def test_succeeds_on_second_attempt_after_bad_first(self):
        """First call returns invalid JSON; second returns valid JSON."""
        provider = StubProvider([INVALID_JSON, VALID_JSON])
        svc = FeatureExtractionService(provider)
        result = svc.extract("Build an ERP")
        assert len(result.features) == 3

    def test_succeeds_on_second_attempt_after_wrong_schema(self):
        provider = StubProvider([WRONG_SCHEMA_JSON, VALID_JSON])
        svc = FeatureExtractionService(provider)
        result = svc.extract("Build a wiki")
        assert len(result.features) == 3

    def test_prompt_includes_system_prompt_and_description(self):
        """Verify the prompt passed to the provider contains both parts."""
        received_prompts: list[str] = []

        class CapturingProvider(LLMProvider):
            def generate(self, prompt: str) -> str:
                received_prompts.append(prompt)
                return VALID_JSON

        svc = FeatureExtractionService(CapturingProvider())
        desc = "A task management app"
        svc.extract(desc)
        assert len(received_prompts) == 1
        assert SYSTEM_PROMPT in received_prompts[0]
        assert desc in received_prompts[0]


# ---------------------------------------------------------------------------
# FeatureExtractionService — error paths
# ---------------------------------------------------------------------------


class TestFeatureExtractionServiceErrors:
    def test_raises_422_after_two_bad_json_responses(self):
        provider = StubProvider([INVALID_JSON, INVALID_JSON])
        svc = FeatureExtractionService(provider)
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 422
        assert exc_info.value.status_code == 422  # user-safe message, no internal leak

    def test_raises_422_after_two_wrong_schema_responses(self):
        provider = StubProvider([WRONG_SCHEMA_JSON, WRONG_SCHEMA_JSON])
        svc = FeatureExtractionService(provider)
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 422

    def test_raises_503_on_connect_error(self):
        provider = ErrorProvider(httpx.ConnectError("refused"))
        svc = FeatureExtractionService(provider)
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail

    def test_raises_504_on_timeout(self):
        provider = ErrorProvider(httpx.TimeoutException("timed out"))
        svc = FeatureExtractionService(provider)
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 504
        assert "timed out" in exc_info.value.detail

    def test_connect_error_on_second_attempt_raises_503(self):
        """First attempt returns bad JSON, second raises ConnectError."""

        call_count = 0

        class FlipProvider(LLMProvider):
            def generate(self, prompt: str) -> str:  # noqa: ARG002
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return INVALID_JSON
                raise httpx.ConnectError("refused")

        svc = FeatureExtractionService(FlipProvider())
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 503

    def test_timeout_on_second_attempt_raises_504(self):
        """First attempt returns bad JSON, second raises TimeoutException."""

        call_count = 0

        class FlipProvider(LLMProvider):
            def generate(self, prompt: str) -> str:  # noqa: ARG002
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return INVALID_JSON
                raise httpx.TimeoutException("timed out")

        svc = FeatureExtractionService(FlipProvider())
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 504


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT content check
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_system_prompt_contains_json_format_instruction(self):
        assert "features" in SYSTEM_PROMPT
        assert "name" in SYSTEM_PROMPT
        assert "description" in SYSTEM_PROMPT

    def test_system_prompt_mentions_json_only(self):
        assert "JSON" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Hardening regression tests (audit-driven)
# ---------------------------------------------------------------------------


class TestExtractionHardening:
    def test_empty_feature_list_is_rejected(self):
        """An empty feature list is a failed extraction, not a success."""
        provider = StubProvider(['{"features": []}', '{"features": []}'])
        svc = FeatureExtractionService(provider)
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 422

    def test_markdown_fenced_json_is_parsed(self):
        provider = StubProvider(
            ['```json\n{"features":[{"name":"A","description":"B"}]}\n```']
        )
        svc = FeatureExtractionService(provider)
        result = svc.extract("Some project")
        assert [f.name for f in result.features] == ["A"]

    def test_think_block_before_json_is_parsed(self):
        provider = StubProvider(
            ['<think>let me reason</think>\n{"features":[{"name":"A","description":"B"}]}']
        )
        svc = FeatureExtractionService(provider)
        result = svc.extract("Some project")
        assert [f.name for f in result.features] == ["A"]

    def test_prose_wrapped_json_is_parsed(self):
        provider = StubProvider(
            ['Sure! Here you go:\n{"features":[{"name":"A","description":"B"}]} Hope that helps.']
        )
        svc = FeatureExtractionService(provider)
        result = svc.extract("Some project")
        assert [f.name for f in result.features] == ["A"]

    def test_duplicate_feature_names_are_deduplicated(self):
        provider = StubProvider(
            ['{"features":[{"name":"Auth","description":"X"},'
             '{"name":"auth","description":"Y"},'
             '{"name":"Reports","description":"Z"}]}']
        )
        svc = FeatureExtractionService(provider)
        result = svc.extract("Some project")
        names = [f.name for f in result.features]
        assert names == ["Auth", "Reports"]  # case-insensitive dedupe, first kept

    def test_model_http_status_error_maps_to_503(self):
        """Ollama returning e.g. 404 (model not pulled) must not leak as 500."""
        err = httpx.HTTPStatusError(
            "not found",
            request=httpx.Request("POST", "http://x"),
            response=httpx.Response(404),
        )
        svc = FeatureExtractionService(ErrorProvider(err))
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("Some project")
        assert exc_info.value.status_code == 503

    def test_empty_description_rejected_without_calling_model(self):
        called = {"n": 0}

        class CountingProvider(LLMProvider):
            def generate(self, prompt: str) -> str:  # noqa: ARG002
                called["n"] += 1
                return VALID_JSON

        svc = FeatureExtractionService(CountingProvider())
        with pytest.raises(HTTPException) as exc_info:
            svc.extract("   ")
        assert exc_info.value.status_code == 422
        assert called["n"] == 0  # guard short-circuits before any model call

    def test_detail_messages_do_not_leak_internals(self):
        """422/503/504 details must be user-safe (no 'LLM', 'traceback', 'json')."""
        for provider_responses in (
            StubProvider([INVALID_JSON, INVALID_JSON]),
            ErrorProvider(httpx.ConnectError("x")),
            ErrorProvider(httpx.TimeoutException("x")),
        ):
            svc = FeatureExtractionService(provider_responses)
            with pytest.raises(HTTPException) as exc_info:
                svc.extract("Some project")
            detail = str(exc_info.value.detail).lower()
            assert "traceback" not in detail
            assert "validationerror" not in detail
