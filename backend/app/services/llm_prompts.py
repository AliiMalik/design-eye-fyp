"""Prompt construction for the design-suggestions module.

The model never sees the image -- only the analytics JSON -- so the prompt
forbids any claim about specific buttons, colours, or copy (BUILD.md section 6).
"""

from __future__ import annotations

import json
from typing import Any

# The model reasons over field names; the designer reading the result has never
# seen them. Grounding stays -- the numbers are still the only evidence allowed --
# but the prose must survive being read by someone who has never opened the docs.
PLAIN_LANGUAGE_RULES = """How to write it:
- Write for a designer, not for an engineer reading a metrics dashboard.
- NEVER print an internal field name. Not "clutter_index", "focus_index",
  "region_saliency", "focus_nodes", "intensity", or "rank". Say what the number
  means instead: "this is the busiest screen in the flow", "attention is spread
  thin rather than landing in one place", "the top third takes most of the
  attention".
- NEVER print raw pixel coordinates like (1590, 480) or long decimals like
  0.8011. Describe the position in words - "top left", "just below the fold",
  "the lower third".
- The 3x3 grid is an internal device. Say "the top of the screen", not "the
  top-center cell"; never write "cell", "grid", or "region" as a noun for it.
- The Clarity Score is the one number the designer already sees, so you may use
  it plainly: "scores 43 out of 100".
- Every suggestion still has to be earned by the numbers. Say what to change and
  why it matters to someone using the screen."""

SYSTEM_PROMPT = f"""You are a senior UX design reviewer. You are given numeric \
outputs from a visual-attention prediction model for a static UI mockup - you \
cannot see the image. Base every statement strictly on the numbers provided; \
never claim to see a specific button, colour, or text. Return 4-6 suggestions \
as JSON matching the schema. Set based_on to the metric that motivated it - \
that field is machine-read, so it keeps the internal name. The prose does not. \
Be specific and actionable - "the top of the screen and the main button are \
pulling almost equally hard, so the eye has no obvious place to start; make the \
button larger or higher in contrast" is good, "improve visual hierarchy" is \
worthless.

{PLAIN_LANGUAGE_RULES}

Return ONLY a JSON object, no prose or code fences, matching exactly:
{{"summary": "string",
 "suggestions": [
   {{"title": "string",
    "detail": "string",
    "severity": "high" | "medium" | "low",
    "based_on": "clarity_score" | "focus_order" | "region_saliency" | "clutter_index"}}
 ]}}"""

METRIC_GLOSSARY = """Metric definitions:
- clarity_score (0-100): overall visual clarity; higher is cleaner and better focused.
- focus_index (0-1): attention concentration. Low means attention is scattered.
- clutter_index (0-1): edge-density clutter. High means visually busy.
- focus_nodes: the top predicted fixation points in order, in image pixels,
  with intensity 0-1. Rank 1 is looked at first.
- region_saliency: mean predicted attention per cell of a 3x3 grid.
- image_meta: pixel dimensions of the mockup."""


def build_user_prompt(analytics: dict[str, Any], user_context: str | None = None) -> str:
    """Assemble the analytics-only user message."""
    payload = {
        "clarity_score": analytics.get("clarity_score"),
        "focus_index": analytics.get("focus_index"),
        "clutter_index": analytics.get("clutter_index"),
        "focus_nodes": analytics.get("focus_nodes", []),
        "region_saliency": analytics.get("region_saliency", {}),
        "image_meta": analytics.get("image_meta", {}),
    }
    parts = [
        METRIC_GLOSSARY,
        "",
        "Analytics for this mockup:",
        json.dumps(payload, indent=2),
    ]
    if user_context:
        parts += ["", "Designer's stated context (treat as background, not as fact "
                      "about the pixels):", user_context.strip()[:1000]]
    parts += ["", "Produce 4-6 grounded, actionable suggestions as JSON."]
    return "\n".join(parts)


REPAIR_PROMPT = (
    "Your previous reply was not valid JSON matching the required schema. "
    "Return ONLY the JSON object, with no code fences and no commentary."
)


# --- flow (multi-screen) --------------------------------------------------
FLOW_SYSTEM_PROMPT = """You are a senior UX design reviewer. You are given numeric outputs from a visual-attention prediction model for EVERY screen of one design flow - you cannot see the images. Base every statement strictly on the numbers provided; never claim to see a specific button, colour, or text.

The point of reviewing the whole flow at once is comparison: say where clarity drops between screens, which step is weakest, and whether attention is consistent across the journey. A per-screen review in isolation cannot do that, so make the cross-screen reading the substance of flow_summary.

Return ONLY a JSON object, no prose or code fences, matching exactly:
{"flow_summary": "string",
 "weakest_screen": <int>,
 "strongest_screen": <int>,
 "screens": [
   {"screen": <int>,
    "headline": "string",
    "suggestions": [
      {"title": "string",
       "detail": "string",
       "severity": "high" | "medium" | "low",
       "based_on": "clarity_score" | "focus_order" | "region_saliency" | "clutter_index"}
    ]}
 ]}

Include one entry for EVERY screen listed, using its screen number. Give exactly {per_screen} suggestions per screen. Set based_on to the metric that motivated it - that field is machine-read, so it keeps the internal name. The prose does not.

{plain_language}"""


# Lets a provider tell a flow review from a single-screen one. MockProvider
# needs the distinction to answer in the right JSON shape.
FLOW_PROMPT_MARKER = "This flow has "


def build_flow_prompt(screens: list[dict[str, Any]], per_screen: int,
                      user_context: str | None = None) -> str:
    """Assemble one analytics-only message covering every screen in the flow."""
    payload = []
    for screen in screens:
        payload.append({
            "screen": screen["screen"],
            "clarity_score": screen.get("clarity_score"),
            "focus_index": screen.get("focus_index"),
            "clutter_index": screen.get("clutter_index"),
            # Trimmed to the leading fixations: sending ten per screen across a
            # long flow is noise that crowds out the cross-screen reading.
            "focus_nodes": (screen.get("focus_nodes") or [])[:5],
            "region_saliency": screen.get("region_saliency", {}),
        })

    parts = [
        METRIC_GLOSSARY,
        "",
        f"{FLOW_PROMPT_MARKER}{len(screens)} screens, in order.",
        json.dumps({"screens": payload}, indent=1),
    ]
    if user_context:
        parts += ["", "Designer's stated context (background only, not fact about "
                      "the pixels):", user_context.strip()[:1000]]
    parts += ["", f"Review the whole flow. Exactly {per_screen} suggestions per "
                  "screen, plus a flow_summary that compares screens."]
    return "\n".join(parts)

