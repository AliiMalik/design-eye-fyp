"""Provider-agnostic LLM adapter for design suggestions (BUILD.md section 6).

Selected by LLM_PROVIDER: anthropic | openai | gemini | mock | none.
The app is fully functional with no LLM configured at all -- "none" returns an
explicit unavailable status and the UI offers a retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.services.llm_prompts import (
    FLOW_PROMPT_MARKER,
    FLOW_SYSTEM_PROMPT,
    PLAIN_LANGUAGE_RULES,
    REPAIR_PROMPT,
    SYSTEM_PROMPT,
    build_flow_prompt,
    build_user_prompt,
)

logger = logging.getLogger(__name__)

VALID_SEVERITY = {"high", "medium", "low"}
VALID_BASIS = {"clarity_score", "focus_order", "region_saliency", "clutter_index"}

# Long flow reviews need real output headroom: 30 screens x 2 suggestions
# measured at ~4.5k output tokens, and the default Gemini ceiling truncates
# mid-JSON at 40 screens.
MAX_OUTPUT_TOKENS = 8192

# One call covering more screens than this risks the output ceiling, so a longer
# flow is split and merged. Measured safe: 30 screens in a single call.
MAX_SCREENS_PER_CALL = 25

# Fewer, sharper points per screen when reviewing a whole flow: 4-6 each reads
# as padding across a dozen screens and inflates the output for no gain.
FLOW_SUGGESTIONS_PER_SCREEN = 2

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-5.1-mini",
    "gemini": "gemini-3.6-flash",
}


class LLMUnavailable(Exception):
    """Provider is not configured or not reachable."""


class LLMTruncated(Exception):
    """The reply hit the output ceiling, so the JSON is incomplete.

    Distinct from a parse failure: re-prompting an over-long response produces
    another over-long response. The caller must reduce scope instead.
    """


def _raise_if_truncated(resp: Any) -> None:
    """Detect Gemini's MAX_TOKENS finish before trying to parse the body."""
    try:
        reason = resp.candidates[0].finish_reason
    except Exception:  # noqa: BLE001 - absent metadata is not an error
        return
    # 2 == MAX_TOKENS in the Gemini finish_reason enum.
    if int(reason) == 2:
        raise LLMTruncated("The model hit its output limit before finishing.")


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


class FlowScreenPayload(BaseModel):
    screen: int
    headline: str = ""
    suggestions: list[SuggestionSchema] = Field(default_factory=list)


class FlowPayload(BaseModel):
    flow_summary: str = ""
    weakest_screen: int | None = None
    strongest_screen: int | None = None
    screens: list[FlowScreenPayload] = Field(default_factory=list)


class LLMProvider(Protocol):
    async def generate(self, system: str, user: str) -> str: ...


class MockProvider:
    """Deterministic valid JSON so the feature is demonstrable with no API key."""

    name = "mock"
    model_name = "mock-reviewer-v1"

    async def generate(self, system: str, user: str) -> str:
        # A flow review asks for a different JSON shape entirely. Returning the
        # single-screen shape here fails validation, which would leave the whole
        # multi-screen feature dead for anyone running without an API key.
        if FLOW_PROMPT_MARKER in user:
            return self._flow(user)
        return self._single(user)

    @staticmethod
    def _flow(user: str) -> str:
        numbers = [int(n) for n in re.findall(r'"screen":\s*(\d+)', user)]
        raw = re.findall(r'"clarity_score":\s*([0-9.]+|null)', user)
        scores = [float(v) if v != "null" else 0.0 for v in raw]
        scores += [0.0] * (len(numbers) - len(scores))

        pairs = list(zip(numbers, scores))
        weakest = min(pairs, key=lambda p: p[1])[0] if pairs else None
        strongest = max(pairs, key=lambda p: p[1])[0] if pairs else None

        screens = []
        for number, clarity in pairs:
            screens.append({
                "screen": number,
                "headline": f"Screen {number} scores {clarity:.1f}/100 for clarity.",
                "suggestions": [
                    {
                        "title": "Give this screen one unmistakable starting point",
                        "detail": "Predicted attention is spread across several peaks "
                                  "of similar strength, so there is no obvious place "
                                  "for the eye to land first. Make the intended "
                                  "primary element larger or higher in contrast.",
                        "severity": "high" if clarity < 50 else "medium",
                        "based_on": "focus_order",
                    },
                    {
                        "title": "Keep the eye moving in the same direction as the flow",
                        "detail": "Where the strongest area of this screen sits far "
                                  "from where the next step begins, the eye has to "
                                  "travel back across the layout. Align the two.",
                        "severity": "medium",
                        "based_on": "region_saliency",
                    },
                ],
            })

        return json.dumps({
            "flow_summary": (
                f"Across these {len(pairs)} screens, attention is least focused on "
                f"screen {weakest} and clearest on screen {strongest}. The drop is "
                f"worth attention because it lands mid-journey, where people are "
                f"most likely to abandon the task."
            ),
            "weakest_screen": weakest,
            "strongest_screen": strongest,
            "screens": screens,
        })

    @staticmethod
    def _single(user: str) -> str:
        match = re.search(r'"clarity_score":\s*([0-9.]+)', user)
        clarity = float(match.group(1)) if match else 0.0

        return json.dumps({
            "summary": (
                f"Attention lands unevenly on this screen, which scores "
                f"{clarity:.0f} out of 100 for clarity. A few spots pull most of "
                f"the eye while whole areas are barely looked at."
            ),
            "suggestions": [
                {
                    "title": "Give the screen one obvious place to start",
                    "detail": "The two strongest spots pull almost equally hard, so "
                              "there is no clear entry point and the eye has to "
                              "choose. Make the element you actually want seen "
                              "first noticeably larger or higher in contrast.",
                    "severity": "high",
                    "based_on": "focus_order",
                },
                {
                    "title": "Lift the areas nobody is looking at",
                    "detail": "Several parts of the layout draw almost no attention. "
                              "If anything important sits there, such as a price, a "
                              "sign-up button or a piece of reassurance, give it "
                              "more visual weight or move it somewhere the eye "
                              "already goes.",
                    "severity": "medium",
                    "based_on": "region_saliency",
                },
                {
                    "title": "Take some visual noise out of the busiest areas",
                    "detail": "This screen is visually busy: a lot of lines, borders, "
                              "and edges competing for the eye. Removing dividers and "
                              "decorative rules lets attention settle on the content "
                              "instead of the furniture.",
                    "severity": "medium",
                    "based_on": "clutter_index",
                },
                {
                    "title": "Group the layout into fewer, larger blocks",
                    "detail": f"At {clarity:.0f} out of 100 there is real room to "
                              "improve. Consolidating scattered elements into a "
                              "smaller number of bigger blocks usually concentrates "
                              "attention and lifts the score.",
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
            max_tokens=MAX_OUTPUT_TOKENS,
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
            max_tokens=MAX_OUTPUT_TOKENS,
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
            generation_config={
                "response_mime_type": "application/json",
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
        )
        resp = await model.generate_content_async(user)
        _raise_if_truncated(resp)
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

    # Latency varies wildly between models -- some Gemini Flash tiers have been
    # measured above 80s on the same prompt. Without a ceiling the caller waits
    # indefinitely on a stalled provider.
    timeout = settings.LLM_TIMEOUT_SECONDS

    try:
        raw = await asyncio.wait_for(
            provider.generate(SYSTEM_PROMPT, user_prompt), timeout=timeout)
        try:
            return _parse(raw), "ok", name, model_name
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("LLM reply failed validation, re-prompting once: %s", exc)
            retry = await asyncio.wait_for(
                provider.generate(SYSTEM_PROMPT, f"{user_prompt}\n\n{REPAIR_PROMPT}"),
                timeout=timeout)
            return _parse(retry), "ok", name, model_name
    except asyncio.TimeoutError:
        logger.error("LLM provider %s (%s) exceeded %ss", name, model_name, timeout)
        return None, "error", name, model_name
    except Exception as exc:  # noqa: BLE001 - suggestions must never break a result
        logger.error("LLM generation failed (provider=%s): %s", name, exc)
        return None, "error", name, model_name


def _parse_flow(raw: str, expected: list[int]) -> FlowPayload:
    """Validate a flow reply and insist every requested screen came back."""
    payload = FlowPayload.model_validate(_extract_json(raw))
    if not payload.screens:
        raise ValueError("Model returned no screens")

    returned = {s.screen for s in payload.screens}
    missing = sorted(set(expected) - returned)
    if missing:
        # Silently rendering 9 of 12 screens would look like a product bug.
        raise ValueError(f"Model omitted screens {missing}")
    return payload


async def generate_flow_suggestions(
    screens: list[dict[str, Any]],
    user_context: str | None = None,
    provider: LLMProvider | None = None,
    per_screen: int = FLOW_SUGGESTIONS_PER_SCREEN,
) -> tuple[FlowPayload | None, str, str, str]:
    """Review an entire flow, ideally in ONE provider call.

    A call per screen would burn the daily quota in a couple of uploads and,
    worse, could not compare screens: each call would see only its own numbers.
    Batching is both cheaper and the only way to say "clarity drops most at
    screen 5". Flows longer than MAX_SCREENS_PER_CALL are split and merged, so
    the count stays proportional to the flow rather than to the screen count.

    Returns ``(payload, status, provider_name, model_name)``.
    """
    provider = provider or build_provider()
    if provider is None:
        return None, "unavailable", settings.LLM_PROVIDER, ""

    name = getattr(provider, "name", settings.LLM_PROVIDER)
    model_name = getattr(provider, "model_name", settings.LLM_MODEL or "")
    if not screens:
        return None, "error", name, model_name

    chunks = [screens[i:i + MAX_SCREENS_PER_CALL]
              for i in range(0, len(screens), MAX_SCREENS_PER_CALL)]
    merged = FlowPayload()
    summaries: list[str] = []

    for chunk in chunks:
        expected = [s["screen"] for s in chunk]
        system = (FLOW_SYSTEM_PROMPT
                  .replace("{per_screen}", str(per_screen))
                  .replace("{plain_language}", PLAIN_LANGUAGE_RULES))
        prompt = build_flow_prompt(chunk, per_screen, user_context)

        try:
            raw = await asyncio.wait_for(
                provider.generate(system, prompt),
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            try:
                part = _parse_flow(raw, expected)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Flow reply failed validation, re-prompting once: %s", exc)
                retry = await asyncio.wait_for(
                    provider.generate(system, f"{prompt}\n\n{REPAIR_PROMPT}"),
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
                part = _parse_flow(retry, expected)
        except LLMTruncated as exc:
            # Re-prompting would produce another over-long reply; say so plainly.
            logger.error("Flow review truncated (%d screens): %s", len(chunk), exc)
            return None, "error", name, model_name
        except asyncio.TimeoutError:
            logger.error("Flow review exceeded %ss", settings.LLM_TIMEOUT_SECONDS)
            return None, "error", name, model_name
        except Exception as exc:  # noqa: BLE001 - suggestions never break a result
            logger.error("Flow review failed (provider=%s): %s", name, exc)
            return None, "error", name, model_name

        merged.screens.extend(part.screens)
        if part.flow_summary:
            summaries.append(part.flow_summary)

    merged.flow_summary = " ".join(summaries)

    # Recompute the extremes from our own numbers rather than trusting the model
    # to rank correctly across chunks it never saw together.
    scored = [(s.get("clarity_score"), s["screen"]) for s in screens
              if s.get("clarity_score") is not None]
    if scored:
        merged.weakest_screen = min(scored)[1]
        merged.strongest_screen = max(scored)[1]

    return merged, "ok", name, model_name

