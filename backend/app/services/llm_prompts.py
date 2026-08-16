"""Prompt construction for the design-suggestions module.

The model never sees the image -- only the analytics JSON -- so the prompt
forbids any claim about specific buttons, colours, or copy (BUILD.md section 6).
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """You are a senior UX design reviewer. You are given numeric \
outputs from a visual-attention prediction model for a static UI mockup - you \
cannot see the image. Base every statement strictly on the numbers provided; \
never claim to see a specific button, colour, or text. Return 4-6 suggestions \
as JSON matching the schema. Each must cite the metric that motivated it. Be \
specific and actionable - "increase the contrast of the top-center region, \
which holds 55% of predicted attention while the mid-center CTA region holds \
63%; these are competing for the first fixation" is good, "improve visual \
hierarchy" is worthless.

Return ONLY a JSON object, no prose or code fences, matching exactly:
{"summary": "string",
 "suggestions": [
   {"title": "string",
    "detail": "string",
    "severity": "high" | "medium" | "low",
    "based_on": "clarity_score" | "focus_order" | "region_saliency" | "clutter_index"}
 ]}"""

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
