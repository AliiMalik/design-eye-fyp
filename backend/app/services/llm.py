"""Provider-agnostic LLM adapter for design suggestions (BUILD.md section 6).

Selected by LLM_PROVIDER: anthropic | openai | gemini | mock | none.
The app is fully functional with no LLM configured at all -- "none" returns an
explicit unavailable status and the UI offers a retry.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.services.llm_prompts import REPAIR_PROMPT, SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

VALID_SEVERITY = {"high", "medium", "low"}
VALID_BASIS = {"clarity_score", "focus_order", "region_saliency", "clutter_index"}

# Model IDs age out fast -- Gemini 1.5 and 2.0 are already shut down and return
# 404, and the 2.5 cluster retires in Oct 2026. Override per deployment with
# LLM_MODEL rather than editing this; these are only the fallbacks.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-5.1-mini",
    "gemini": "gemini-3.5-flash",
}


class LLMUnavailable(Exception):
    """Provider is not configured or not reachable."""


class SuggestionSchema(BaseModel):
    title: str
    detail: str
    severity: str = "medium"
    based_on: str = "clarity_score"

    @field_validator("severity")
    @classmethod
    def _sev(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in VALID_SEVERITY else "medium"

    @field_validator("based_on")
    @classmethod
    def _basis(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in VALID_BASIS else "clarity_score"


class SuggestionPayload(BaseModel):
    summary: str = ""
    suggestions: list[SuggestionSchema] = Field(default_factory=list)


class LLMProvider(Protocol):
    async def generate(self, system: str, user: str) -> str: ...


class MockProvider:
    """Deterministic valid JSON so the feature is demonstrable with no API key."""

    name = "mock"
    model_name = "mock-reviewer-v1"

    async def generate(self, system: str, user: str) -> str:
        match = re.search(r'"clarity_score":\s*([0-9.]+)', user)
        clarity = float(match.group(1)) if match else 0.0

        return json.dumps({
            "summary": (
                f"Predicted attention is measurably uneven: the mockup scores "
                f"{clarity:.1f}/100 for clarity. Attention concentrates in a small "
                f"number of peaks while several regions receive almost none."
            ),
            "suggestions": [
                {
                    "title": "Resolve competition between the top two fixation points",
                    "detail": "The first- and second-ranked focus nodes have similar "
                              "intensity, so the eye has no unambiguous entry point. "
                              "Increase the size or contrast of the intended primary "
                              "element so its predicted intensity leads clearly.",
                    "severity": "high",
                    "based_on": "focus_order",
                },
                {
                    "title": "Raise attention in the under-weighted grid regions",
                    "detail": "Several cells of the 3x3 region grid hold a small share "
                              "of predicted attention. If any carries a conversion-"
                              "critical element, give it more visual weight or move it "
                              "into a higher-attention band.",
                    "severity": "medium",
                    "based_on": "region_saliency",
                },
                {
                    "title": "Reduce edge density in the densest areas",
                    "detail": "The clutter index indicates a high proportion of high-"
                              "gradient pixels. Removing dividers, borders, and "
                              "decorative rules lowers competing edges and lets "
                              "attention settle on content.",
                    "severity": "medium",
                    "based_on": "clutter_index",
                },
                {
                    "title": "Tighten visual hierarchy to lift the Clarity Score",
                    "detail": f"At {clarity:.1f}/100 there is measurable headroom. "
                              "Consolidating the layout into fewer, larger blocks "
                              "typically concentrates predicted attention and raises "
                              "the focus component of the score.",
                    "severity": "low",
                    "based_on": "clarity_score",
                },
            ],
        })


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model_name = settings.LLM_MODEL or DEFAULT_MODELS["anthropic"]

    async def generate(self, system: str, user: str) -> str:
        resp = await self._client.messages.create(
            model=self.model_name,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise LLMUnavailable("OPENAI_API_KEY is not set")
        import openai
        self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model_name = settings.LLM_MODEL or DEFAULT_MODELS["openai"]

    async def generate(self, system: str, user: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model_name,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.LLM_MODEL or DEFAULT_MODELS["gemini"]
        self._genai = genai

    async def generate(self, system: str, user: str) -> str:
        model = self._genai.GenerativeModel(
            self.model_name,
            system_instruction=system,
            generation_config={"response_mime_type": "application/json"},
        )
        resp = await model.generate_content_async(user)
        return resp.text or ""


def build_provider(name: str | None = None) -> LLMProvider | None:
    """Instantiate the configured provider; None means suggestions are off."""
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "none":
        return None
    try:
        if name == "mock":
            return MockProvider()
        if name == "anthropic":
            return AnthropicProvider()
        if name == "openai":
            return OpenAIProvider()
        if name == "gemini":
            return GeminiProvider()
    except LLMUnavailable as exc:
        logger.warning("LLM provider %s unavailable: %s", name, exc)
        return None
    except ImportError:
        # Provider SDKs are optional; see backend/requirements-llm.txt.
        logger.warning(
            "LLM provider '%s' is configured but its SDK is not installed. "
            "Run: pip install -r requirements-llm.txt", name,
        )
        return None
    except Exception as exc:  # noqa: BLE001 - a bad SDK must not break startup
        logger.error("Failed to initialise LLM provider %s: %s", name, exc)
        return None
    logger.warning("Unknown LLM provider: %s", name)
    return None


def _extract_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object out of a model reply, tolerating code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON object found in the model reply")


def _parse(raw: str) -> SuggestionPayload:
    payload = SuggestionPayload.model_validate(_extract_json(raw))
    if not payload.suggestions:
        raise ValueError("Model returned zero suggestions")
    return payload


async def generate_suggestions(
    analytics: dict[str, Any],
    user_context: str | None = None,
    provider: LLMProvider | None = None,
) -> tuple[SuggestionPayload | None, str, str, str]:
    """Generate suggestions.

    Returns (payload, status, provider_name, model_name) where status is one of
    ok | unavailable | error. Re-prompts exactly once on a parse failure.
    """
    provider = provider or build_provider()
    if provider is None:
        return None, "unavailable", settings.LLM_PROVIDER, ""

    name = getattr(provider, "name", settings.LLM_PROVIDER)
    model_name = getattr(provider, "model_name", settings.LLM_MODEL or "")
    user_prompt = build_user_prompt(analytics, user_context)

    try:
        raw = await provider.generate(SYSTEM_PROMPT, user_prompt)
        try:
            return _parse(raw), "ok", name, model_name
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("LLM reply failed validation, re-prompting once: %s", exc)
            retry = await provider.generate(
                SYSTEM_PROMPT, f"{user_prompt}\n\n{REPAIR_PROMPT}")
            return _parse(retry), "ok", name, model_name
    except Exception as exc:  # noqa: BLE001 - suggestions must never break a result
        logger.error("LLM generation failed (provider=%s): %s", name, exc)
        return None, "error", name, model_name
