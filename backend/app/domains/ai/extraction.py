"""Feature extraction service.

Turns a project description into a validated, de-duplicated list of candidate
features by calling the configured LLM provider. The parser is deliberately
tolerant of common LLM output decorations (markdown fences, <think> reasoning
blocks, surrounding prose) because a locally hosted model does not always honor
"return only JSON" instructions. All failure modes are mapped to safe HTTP
errors; raw provider/parse exceptions are never allowed to propagate.
"""

import json
import re

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.domains.ai.provider import LLMProvider
from app.domains.ai.schemas import ExtractedFeature, FeatureExtractionResponse

SYSTEM_PROMPT = (
    "You are a software requirements analyst. Given a project description, extract a list of"
    " discrete, high-level software features.\n"
    "Return ONLY valid JSON in this exact format with no other text, explanation, or markdown:\n"
    '{"features": [{"name": "Feature Name", "description": "Feature description"}]}\n'
    "Extract between 3 and 10 features. Each feature should be a distinct, meaningful capability."
)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json_object(raw: str) -> str:
    """Best-effort extraction of the JSON object from a raw model response.

    Handles clean JSON, markdown-fenced JSON, responses preceded by a <think>
    reasoning block, and JSON embedded in surrounding prose. Returns the JSON
    substring (unparsed); raises ValueError if nothing object-like is found.
    """
    text = _THINK_BLOCK.sub("", raw).strip()

    fenced = _CODE_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    # If the whole thing already looks like a JSON object, use it as-is.
    if text.startswith("{") and text.endswith("}"):
        return text

    # Otherwise, grab the first balanced {...} span.
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced JSON object in model response")


def _parse(raw: str) -> FeatureExtractionResponse:
    """Parse + validate a raw response into a FeatureExtractionResponse.

    Raises ValidationError / json.JSONDecodeError / ValueError on bad output so
    the caller can decide whether to retry.
    """
    candidate = _extract_json_object(raw)
    return FeatureExtractionResponse.model_validate_json(candidate)


def _dedupe(features: list[ExtractedFeature]) -> list[ExtractedFeature]:
    """Drop features with duplicate (case-insensitive, trimmed) names, keeping first."""
    seen: set[str] = set()
    unique: list[ExtractedFeature] = []
    for feature in features:
        key = feature.name.strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(feature)
    return unique


class FeatureExtractionService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def extract(self, project_description: str) -> FeatureExtractionResponse:
        if not project_description or not project_description.strip():
            raise HTTPException(
                status_code=422,
                detail="Project description is empty; nothing to extract.",
            )

        prompt = f"{SYSTEM_PROMPT}\n\nProject description:\n{project_description}"

        try:
            parsed = self._attempt_with_retry(prompt)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="The AI model did not return features in the expected format.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504, detail="AI service request timed out."
            ) from exc
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=503, detail="AI service is unavailable."
            ) from exc
        except httpx.HTTPStatusError as exc:
            # Ollama returns 404 when the configured model is not pulled, etc.
            raise HTTPException(
                status_code=503,
                detail="AI service rejected the request (model may be unavailable).",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503, detail="AI service communication error."
            ) from exc

        unique = _dedupe(parsed.features)
        if not unique:
            raise HTTPException(
                status_code=422,
                detail="The AI model returned no usable features for this description.",
            )
        return FeatureExtractionResponse(features=unique)

    def _attempt_with_retry(self, prompt: str) -> FeatureExtractionResponse:
        """Call the provider, retrying once on a parse/validation failure.

        Network/HTTP errors are not retried here; they propagate to extract()
        for mapping. Parse/validation errors trigger exactly one retry.
        """
        try:
            return _parse(self.provider.generate(prompt))
        except (ValidationError, json.JSONDecodeError, ValueError):
            # One retry — the model may format correctly on a second pass.
            return _parse(self.provider.generate(prompt))
