"""Dark-mode compensation for the saliency checkpoint.

The trained model reads dark interfaces badly. Measured on one synthetic layout
with only the colour scheme changed and edge density held constant (0.0221 vs
0.0223), the Clarity Score moved 89.28 -> 37.40, entirely through the focus
term. Inverting the calibration set costs 10-19% of focus_raw on pixel-identical
content, so this is the checkpoint's bias and not a property of the designs.

It was confirmed on a real screen before this module was written: the same Google
Classroom view scored 27.4 dark and 65.4 light, and 98% of that 38-point gap came
from focus, with clutter almost unchanged (0.320 vs 0.291).

Two things are probably at work, and inversion addresses both:

1. The checkpoint was trained on light-mode UI, so dark input is out of domain.
2. ``letterbox_with_meta`` pads to 224x224 with WHITE. A phone screen is 54%
   padding at 9:19.5, so a dark upload reaches the model as a black island in a
   white field -- a violent boundary that exists nowhere in the training data.
   Inverting makes the content agree with its own padding.

The inversion is applied to the model's INPUT ONLY. Every reported number that
does not come from the model -- edge density, clutter, the heatmap overlay -- is
computed on the original pixels. Edge density is inversion-invariant anyway
(Sobel measures gradient magnitude), which the tests assert.

This is a documented workaround for a training-data gap, not a fix for it. The
honest repair is a checkpoint trained on dark UI; until then the result records
``ui_theme`` so the compensation is never silent.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Mean luminance below which an upload is treated as dark-themed.
#
# Chosen from measurement, not taste. Across all 25 light-mode screens in
# inputs/ the lowest mean luminance is 166.3 (synth_text_wall); dark-mode screens
# measure around 20-30. The threshold sits in the empty band between, with ~66
# of margin to the nearest light screen and ~76 to the dark reference. The
# asymmetry matters: a false positive here would inverting a light screen and
# cost it ~55 points, so the gate is kept well clear of real light designs.
#
# KNOWN LIMITATION: any hard gate is a discontinuity. Sweeping a synthetic
# design's background across the threshold, clarity steps ~12 points as the
# compensation switches on (67.6 just below, 56.0 just above). Real designs do
# not live there -- the nearest measured light screen is 166 and dark screens sit
# near 25 -- so the cliff falls in an empty part of the distribution. A mid-grey
# interface scored near the gate should be treated with less confidence.
DARK_UI_LUMA = 100.0


def mean_luminance(img: Image.Image) -> float:
    """Mean 0-255 luminance of an image."""
    return float(np.asarray(img.convert("L"), dtype=np.float32).mean())


def is_dark_ui(img: Image.Image) -> bool:
    return mean_luminance(img) < DARK_UI_LUMA


def detect_theme(img: Image.Image) -> str:
    """``"dark"`` or ``"light"``, recorded on the result for transparency."""
    return "dark" if is_dark_ui(img) else "light"


def for_model(img: Image.Image, dark: bool) -> Image.Image:
    """The image the checkpoint should actually see.

    Returns the original unchanged for light interfaces, so the overwhelmingly
    common path is untouched and cannot regress.

    Only the LUMINANCE channel is flipped, not RGB. Inverting RGB turns a blue
    primary button orange, which is not "the same design in light mode" and
    throws away the colour the model was trained to react to. Measured on the
    sparse dark screen: 37.40 uncompensated, 79.21 via RGB inversion, 79.98
    preserving hue.
    """
    if not dark:
        return img
    lab = np.asarray(img.convert("LAB"), dtype=np.uint8).copy()
    lab[..., 0] = 255 - lab[..., 0]
    return Image.fromarray(lab, mode="LAB").convert("RGB")
