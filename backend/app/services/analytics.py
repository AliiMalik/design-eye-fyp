"""Clarity Score, Focus Order, and region grid (BUILD.md section 5).

All tunable constants live at the top of this module so calibration is a
single-file change (see scripts/calibrate_clarity.py).

Resolution invariance
---------------------
Entropy and edge density are both computed on fixed-size reductions of the
inputs rather than on raw pixels. Computed on raw pixels, the same design
uploaded at 2x resolution scores differently -- which would make the A/B
comparison feature meaningless. See docs/DEVIATIONS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# --- tunable constants (calibration targets: clean > 75, cluttered < 40) ---
# Set by scripts/calibrate_clarity.py against inputs/samples/; see docs/DEVIATIONS.md.
FOCUS_WEIGHT = 0.75          # calibrated up from the SDS 0.65
CLUTTER_WEIGHT = 0.25        # calibrated down from the SDS 0.35
EDGE_THRESHOLD = 50.0        # Sobel magnitude above which a pixel counts as an edge
EDGE_DENSITY_SCALE = 0.215   # edge density that maps to fully cluttered

# Raw entropy-based focus occupies a narrow band in practice (roughly 0.03-0.20),
# so the SDS formula alone tops out near 30/100 and can never reach the >75 band
# the test cases require. These bounds stretch the observed range onto [0,1]
# before weighting. A grid search returned a wider margin at FOCUS_RAW_MAX=0.16,
# but that saturates every clean sample at 1.0 and collapses the distinction
# between a good design and a great one, so the looser bound is kept.
FOCUS_RAW_MIN = 0.04
FOCUS_RAW_MAX = 0.19
ENTROPY_GRID = 224           # fixed grid for entropy (resolution invariance)
EDGE_LONG_SIDE = 512         # fixed long side for edge density
NMS_RADIUS = 20              # tuned up from 10px in Sprint 4 (SDS Table 12)
NMS_RADIUS_FRACTION = 0.08   # floor scales with image size; see extract_focus_order
TOP_N_FOCUS_NODES = 5
SCANPATH_NODES = 10         # longer sequence, animation only; focus_nodes stays 5
FOCUS_BLUR_SIGMA = 2.0

# Fixation timing for the simulated scanpath. Typical reading fixations run
# 200-300ms with ~30-50ms saccades between them (Rayner 1998). The model
# predicts WHERE attention lands, not WHEN, so dwell is scaled by predicted
# strength as a presentation choice -- it is not a temporal prediction.
DWELL_MIN_MS = 180
DWELL_MAX_MS = 320
SACCADE_MS = 40

REGION_KEYS = [
    "top_left", "top_center", "top_right",
    "mid_left", "mid_center", "mid_right",
    "bot_left", "bot_center", "bot_right",
]


@dataclass
class FocusNodeData:
    x: int
    y: int
    rank: int
    intensity: float

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "rank": self.rank,
                "intensity": round(self.intensity, 4)}


@dataclass
class AnalyticsResult:
    clarity_score: float
    focus_index: float
    clutter_index: float
    region_saliency: dict[str, float]
    focus_nodes: list[FocusNodeData] = field(default_factory=list)
    scanpath_nodes: list[FocusNodeData] = field(default_factory=list)


def _resize_long_side(gray: np.ndarray, long_side: int) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = long_side / float(max(h, w))
    if scale >= 1.0:
        return gray
    return cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)


def compute_focus_index(saliency: np.ndarray) -> float:
    """Attention concentration in [0, 1]; 1 means perfectly concentrated.

    ``focus = 1 - entropy / log2(num_pixels)`` on a fixed ENTROPY_GRID.
    """
    grid = cv2.resize(saliency.astype(np.float32), (ENTROPY_GRID, ENTROPY_GRID),
                      interpolation=cv2.INTER_AREA)
    grid = np.clip(grid, 0.0, None)
    total = float(grid.sum())
    if total <= 1e-12:
        return 0.0

    sal_norm = grid / total
    entropy = float(-np.sum(sal_norm * np.log2(sal_norm + 1e-12)))
    max_entropy = float(np.log2(grid.size))
    return float(np.clip(1.0 - entropy / max_entropy, 0.0, 1.0))


def compute_edge_density(image_rgb: np.ndarray) -> float:
    """Fraction of pixels whose Sobel gradient magnitude exceeds EDGE_THRESHOLD."""
    if image_rgb.ndim == 3:
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_rgb
    gray = _resize_long_side(gray.astype(np.uint8), EDGE_LONG_SIDE)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)
    return float(np.mean(magnitude > EDGE_THRESHOLD))


def normalise_focus(focus_raw: float) -> float:
    """Stretch the raw entropy-based focus onto [0, 1] using the calibrated band."""
    span = FOCUS_RAW_MAX - FOCUS_RAW_MIN
    if span <= 1e-9:
        return float(np.clip(focus_raw, 0.0, 1.0))
    return float(np.clip((focus_raw - FOCUS_RAW_MIN) / span, 0.0, 1.0))


def compute_clutter_index(image_rgb: np.ndarray) -> float:
    """Edge-density clutter mapped into [0, 1]."""
    return float(np.clip(compute_edge_density(image_rgb) / EDGE_DENSITY_SCALE, 0.0, 1.0))


def compute_clarity_score(focus_index: float, clutter_index: float) -> float:
    """Blend concentration and cleanliness into a 0-100 Clarity Score."""
    score = 100.0 * (FOCUS_WEIGHT * focus_index + CLUTTER_WEIGHT * (1.0 - clutter_index))
    return float(round(np.clip(score, 0.0, 100.0), 2))


def nms_radius_for(height: int, width: int) -> int:
    """Suppression radius in original pixels.

    The SDS records a flat 20px radius (Sprint 4, tuned up from 10px). Applied
    literally to a tall page export, all five peaks land inside a single hot
    blob -- a 3294px-tall mockup returned five nodes spanning 110px of one
    headline, which is useless as a gaze sequence. The 20px value is kept as the
    floor and scaled by NMS_RADIUS_FRACTION of the long side so nodes stay
    spatially distinct at any resolution. See docs/DEVIATIONS.md.
    """
    return max(NMS_RADIUS, int(NMS_RADIUS_FRACTION * max(height, width)))


def extract_focus_order(saliency: np.ndarray, top_n: int = TOP_N_FOCUS_NODES,
                        radius: int | None = None) -> list[FocusNodeData]:
    """Top-N saliency peaks via non-maximum suppression, ranked by intensity.

    Coordinates are in ORIGINAL image pixel space. No duplicate coordinates
    (SDS test case TC-09).
    """
    sal = cv2.GaussianBlur(saliency.astype(np.float32), (0, 0), FOCUS_BLUR_SIGMA)
    h, w = sal.shape[:2]
    radius = radius if radius is not None else nms_radius_for(h, w)
    working = sal.copy()
    nodes: list[FocusNodeData] = []
    taken: set[tuple[int, int]] = set()

    for rank in range(1, top_n + 1):
        idx = int(np.argmax(working))
        y, x = np.unravel_index(idx, working.shape)
        intensity = float(working[y, x])
        if intensity <= 0.0:
            break  # nothing salient left to report
        if (int(x), int(y)) in taken:
            break

        taken.add((int(x), int(y)))
        nodes.append(FocusNodeData(x=int(x), y=int(y), rank=rank, intensity=intensity))

        # Suppress a NMS_RADIUS neighbourhood so the next peak is distinct.
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        working[y0:y1, x0:x1] = -1.0

    return nodes


def dwell_ms_for(intensity: float) -> int:
    """Dwell time for a fixation, scaled by predicted strength."""
    span = DWELL_MAX_MS - DWELL_MIN_MS
    return int(round(DWELL_MIN_MS + span * float(np.clip(intensity, 0.0, 1.0))))


def scanpath_timeline(nodes: list[FocusNodeData]) -> list[dict]:
    """Absolute start/end times for each fixation, in milliseconds.

    Shared by the animated player, the video renderer, and the PDF filmstrip so
    all three show the identical sequence.
    """
    timeline: list[dict] = []
    clock = 0
    for i, node in enumerate(nodes):
        if i > 0:
            clock += SACCADE_MS
        dwell = dwell_ms_for(node.intensity)
        timeline.append({
            "rank": node.rank, "x": node.x, "y": node.y,
            "intensity": round(node.intensity, 4),
            "start_ms": clock, "dwell_ms": dwell, "end_ms": clock + dwell,
        })
        clock += dwell
    return timeline


def total_scanpath_ms(nodes: list[FocusNodeData]) -> int:
    return scanpath_timeline(nodes)[-1]["end_ms"] if nodes else 0


def compute_region_saliency(saliency: np.ndarray) -> dict[str, float]:
    """Mean saliency per cell of a 3x3 grid, keyed top_left .. bot_right."""
    grid = cv2.resize(saliency.astype(np.float32), (3, 3), interpolation=cv2.INTER_AREA)
    flat = grid.flatten()
    return {key: float(round(val, 4)) for key, val in zip(REGION_KEYS, flat)}


def analyse(saliency: np.ndarray, image_rgb: np.ndarray) -> AnalyticsResult:
    """Run the full analytics suite for one mockup.

    ``focus_index`` is reported normalised, so the value the UI shows and the
    value the LLM reasons over are the same one that feeds the Clarity Score.
    """
    focus_index = normalise_focus(compute_focus_index(saliency))
    clutter_index = compute_clutter_index(image_rgb)

    # One extraction, two views. The peak search is greedy and deterministic, so
    # the first TOP_N_FOCUS_NODES of the longer sequence are identical to running
    # it with top_n=5 -- the animation can never disagree with the Focus Order
    # list, and TC-09 keeps seeing exactly 5 nodes.
    scanpath = extract_focus_order(saliency, top_n=SCANPATH_NODES)

    return AnalyticsResult(
        clarity_score=compute_clarity_score(focus_index, clutter_index),
        focus_index=float(round(focus_index, 4)),
        clutter_index=float(round(clutter_index, 4)),
        region_saliency=compute_region_saliency(saliency),
        focus_nodes=scanpath[:TOP_N_FOCUS_NODES],
        scanpath_nodes=scanpath,
    )
