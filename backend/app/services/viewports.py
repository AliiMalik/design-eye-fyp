"""Scroll-aware segmentation for full-page exports.

A designer who exports a whole scrolling page hands us an image with an aspect
ratio no human ever sees at once. Scoring it as a single frame is wrong twice
over, and both failures are mechanical rather than subtle:

1. Preprocessing letterboxes to 224x224. At 15:1 the page occupies a 14x224
   strip -- 6.2% of the model's input, the other 94% white padding -- so the
   saliency map is derived from almost nothing.
2. Edge density is measured at a fixed 512px long side. At 15:1 that leaves a
   33x512 grid, crushing every detail into a gradient, so clutter saturates.

Measured on a 7-viewport page, both terms clamp (focus_raw 0.026 < FOCUS_RAW_MIN,
clutter 1.0) and the Clarity Score is forced to 0.0 arithmetically -- a number
that says nothing about the design. Segmenting the same page into viewports
returns 25.7 / 36.9 / 42.1 / 31.5 / 53.8 / 62.6 / 59.5 instead.

The segmentation must happen BEFORE inference. Computing focus per band on a
whole-page saliency map would be one forward pass instead of N, but that map is
the starved one -- there is no information in it to partition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Height of one viewport as a multiple of the image width. A phone is portrait,
# a desktop viewport is wider than it is tall.
VIEWPORT_ASPECTS: dict[str, float] = {
    "phone": 19.5 / 9,     # 2.167 -- iPhone-class, the common Figma frame
    "tablet": 4 / 3,       # 1.333
    "desktop": 10 / 16,    # 0.625
}
DEFAULT_DEVICE = "phone"

# Segment once the page is meaningfully taller than one viewport. Measured
# degradation begins immediately above 1.0 viewports and both score terms clamp
# by ~2.3, so the trigger sits low deliberately.
SEGMENT_TRIGGER = 1.35

# Neighbouring viewports overlap so an element straddling a boundary is still
# whole somewhere. Scrolling is continuous; hard cuts would invent a seam that
# the design does not have.
VIEWPORT_OVERLAP = 0.12

# One upload must not be able to queue unbounded inference.
MAX_VIEWPORTS = 12

# Below this share of the model's 224x224 input, the letterboxed content is too
# small a sliver for the result to mean anything -- 0.25 is roughly 4:1.
#
# This is deliberately a GEOMETRY test, not a clamp test. Clamping cannot tell
# the two cases apart: the calibration set's synth_data_table and
# synth_dense_dashboard both report focus 0.0000 with clutter 1.0000 and score
# 0.00, and those are correct readings of genuinely unusable designs that TC-08
# depends on. An unscoreable page looks identical in the metrics and different
# only in its shape.
MIN_CONTENT_FRACTION = 0.25


def letterbox_content_fraction(width: int, height: int, side: int = 224) -> float:
    """Share of the model's square input the image occupies once letterboxed.

    1.0 for a square upload, 0.46 for a phone viewport, 0.062 for a 15:1
    full-page export -- which is why such a page cannot be scored whole.
    """
    scale = min(side / float(width), side / float(height))
    cw = max(1, int(width * scale))
    ch = max(1, int(height * scale))
    return (cw * ch) / float(side * side)


def is_scoreable(width: int, height: int) -> bool:
    """Whether a frame of this shape carries enough pixels to score at all.

    Segmentation fixes tall pages; this also catches the shapes it cannot fix,
    such as an ultra-wide panorama export, where the starvation is horizontal.
    """
    return letterbox_content_fraction(width, height) >= MIN_CONTENT_FRACTION


class ViewportError(ValueError):
    """Raised for a device name we do not know."""


@dataclass(frozen=True)
class Viewport:
    """One viewport-sized slice of a long page, in original image pixels."""

    index: int          # 1-based, top to bottom
    top: int
    bottom: int
    image: Image.Image

    @property
    def height(self) -> int:
        return self.bottom - self.top


def viewport_aspect(device: str) -> float:
    try:
        return VIEWPORT_ASPECTS[device]
    except KeyError as exc:
        raise ViewportError(
            f"Unknown device '{device}'. Expected one of "
            f"{', '.join(sorted(VIEWPORT_ASPECTS))}."
        ) from exc


def default_device(width: int, height: int) -> str:
    """Best guess at the viewing device from the image alone.

    Deliberately crude, because it cannot be made reliable: a phone frame
    exported at 2.5x is 2325px wide, overlapping desktop widths exactly, so
    absolute size carries no signal. Orientation does. The caller can override,
    which is why this only has to be reasonable rather than right.
    """
    return "desktop" if width > height else DEFAULT_DEVICE


def viewport_height(width: int, device: str = DEFAULT_DEVICE) -> int:
    return max(1, int(round(width * viewport_aspect(device))))


def count_viewports(width: int, height: int, device: str = DEFAULT_DEVICE) -> float:
    """How many viewports tall this page is. 1.0 means it fits one screen."""
    return height / float(viewport_height(width, device))


def should_segment(width: int, height: int, device: str = DEFAULT_DEVICE) -> bool:
    return count_viewports(width, height, device) >= SEGMENT_TRIGGER


def slice_viewports(img: Image.Image, device: str = DEFAULT_DEVICE,
                    limit: int = MAX_VIEWPORTS) -> list[Viewport]:
    """Cut a long page into overlapping viewport-sized slices, top to bottom.

    Returns a single full-image viewport when the page already fits one screen,
    so callers can treat the segmented and unsegmented paths identically.
    """
    width, height = img.size
    if not should_segment(width, height, device):
        return [Viewport(index=1, top=0, bottom=height, image=img)]

    vh = viewport_height(width, device)
    step = max(1, int(round(vh * (1.0 - VIEWPORT_OVERLAP))))

    # The final slice is pulled UP to end exactly at the page bottom rather than
    # clipped short. A clipped tail tile keeps the pathological aspect ratio this
    # whole module exists to remove -- on a 7-viewport page it came out at 1.82:1
    # instead of 2.17:1 and was scored as if it were a screen.
    tops: list[int] = []
    top = 0
    while len(tops) < limit:
        if top + vh >= height:
            tops.append(max(0, height - vh))
            break
        tops.append(top)
        top += step

    tops = sorted({t for t in tops})

    slices: list[Viewport] = []
    for i, t in enumerate(tops, start=1):
        b = min(height, t + vh)
        if b - t < 16:
            continue
        slices.append(Viewport(index=i, top=t, bottom=b,
                               image=img.crop((0, t, width, b))))

    dropped = count_viewports(width, height, device) - len(slices)
    if dropped > 0.5:
        logger.info("Page is %.1f viewports tall; scoring the first %d",
                    count_viewports(width, height, device), len(slices))
    return slices


@dataclass
class ViewportScore:
    """What one viewport scored, and where it sits on the page."""

    index: int
    top: int
    bottom: int
    clarity_score: float
    focus_index: float
    clutter_index: float

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "top": self.top,
            "bottom": self.bottom,
            "clarity_score": round(self.clarity_score, 2),
            "focus_index": round(self.focus_index, 4),
            "clutter_index": round(self.clutter_index, 4),
        }


@dataclass
class Aggregate:
    clarity_score: float
    focus_index: float
    clutter_index: float
    weakest_index: int
    strongest_index: int


def aggregate_scores(scores: list[ViewportScore]) -> Aggregate:
    """Combine per-viewport scores into the headline number.

    An unweighted mean. Weighting the upper viewports more heavily would model
    the fact that fewer people scroll to the bottom, but that decay curve would
    be an assumption of ours rather than anything the model predicts -- the same
    line the scanpath timing sits on. The per-viewport breakdown is reported
    alongside, so nothing is hidden behind the average.
    """
    if not scores:
        raise ValueError("Cannot aggregate an empty viewport list")

    weakest = min(scores, key=lambda s: s.clarity_score)
    strongest = max(scores, key=lambda s: s.clarity_score)
    n = float(len(scores))
    return Aggregate(
        clarity_score=round(sum(s.clarity_score for s in scores) / n, 2),
        focus_index=round(sum(s.focus_index for s in scores) / n, 4),
        clutter_index=round(sum(s.clutter_index for s in scores) / n, 4),
        weakest_index=weakest.index,
        strongest_index=strongest.index,
    )


def stitch_saliency(maps: list[tuple[Viewport, np.ndarray]],
                    width: int, height: int) -> np.ndarray:
    """Reassemble per-viewport saliency into one full-page map for display.

    Used for the heatmap overlay, Focus Order and the replay, so the numbered
    dots still land on the page the user actually uploaded. Overlaps are
    averaged with a linear feather; a hard join would leave a visible band
    across the heatmap at every viewport boundary.
    """
    total = np.zeros((height, width), dtype=np.float32)
    weight = np.zeros((height, width), dtype=np.float32)

    for vp, sal in maps:
        h = vp.bottom - vp.top
        if sal.shape[0] != h or sal.shape[1] != width:
            sal = np.asarray(
                Image.fromarray((np.clip(sal, 0, 1) * 255).astype(np.uint8))
                .resize((width, h), Image.BILINEAR), dtype=np.float32) / 255.0

        feather = np.ones(h, dtype=np.float32)
        ramp = max(1, int(h * VIEWPORT_OVERLAP))
        if vp.top > 0:
            feather[:ramp] = np.linspace(0.0, 1.0, ramp, dtype=np.float32)
        if vp.bottom < height:
            feather[-ramp:] = np.linspace(1.0, 0.0, ramp, dtype=np.float32)

        total[vp.top:vp.bottom] += sal.astype(np.float32) * feather[:, None]
        weight[vp.top:vp.bottom] += feather[:, None]

    np.divide(total, weight, out=total, where=weight > 1e-6)
    return np.clip(total, 0.0, 1.0)
