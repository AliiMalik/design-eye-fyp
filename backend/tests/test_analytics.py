"""Analytics test cases: TC-07, TC-08, TC-09, plus letterbox alignment."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.config import settings
from app.ml.inference import build_overlay, load_model, predict_saliency
from app.ml.preprocess import IMG_SIZE, letterbox_with_meta, preprocess
from app.services.analytics import (
    CLUTTER_WEIGHT,
    FOCUS_WEIGHT,
    NMS_RADIUS,
    TOP_N_FOCUS_NODES,
    analyse,
    compute_clarity_score,
    compute_region_saliency,
    extract_focus_order,
    nms_radius_for,
)
from tests.conftest import make_png, upload_and_wait

CLEAN_TARGET = 75.0
CLUTTERED_TARGET = 40.0


@pytest.fixture(scope="module")
def model():
    return load_model(settings.MODEL_PATH)


# --- TC-07 / TC-08: calibration bands --------------------------------------
def test_tc07_clean_designs_score_above_75(model, sample_paths):
    """TC-07: a clean, focused design scores > 75."""
    paths = sample_paths["clean"]
    if not paths:
        pytest.skip("no calibration samples; run scripts/make_samples.py")

    scores = {}
    for path in paths:
        img = Image.open(path).convert("RGB")
        out = predict_saliency(img)
        scores[path.name] = analyse(out.saliency, np.array(img, dtype=np.uint8)).clarity_score

    failures = {k: v for k, v in scores.items() if v <= CLEAN_TARGET}
    assert not failures, f"clean samples at or below {CLEAN_TARGET}: {failures}"


def test_tc08_cluttered_designs_score_below_40(model, sample_paths):
    """TC-08: a high-entropy, edge-dense design scores < 40."""
    paths = sample_paths["cluttered"]
    if not paths:
        pytest.skip("no calibration samples; run scripts/make_samples.py")

    scores = {}
    for path in paths:
        img = Image.open(path).convert("RGB")
        out = predict_saliency(img)
        scores[path.name] = analyse(out.saliency, np.array(img, dtype=np.uint8)).clarity_score

    failures = {k: v for k, v in scores.items() if v >= CLUTTERED_TARGET}
    assert not failures, f"cluttered samples at or above {CLUTTERED_TARGET}: {failures}"


def test_clean_scores_strictly_above_cluttered(model, sample_paths):
    if not sample_paths["clean"] or not sample_paths["cluttered"]:
        pytest.skip("no calibration samples")

    def score(path):
        img = Image.open(path).convert("RGB")
        out = predict_saliency(img)
        return analyse(out.saliency, np.array(img, dtype=np.uint8)).clarity_score

    worst_clean = min(score(p) for p in sample_paths["clean"])
    best_cluttered = max(score(p) for p in sample_paths["cluttered"])
    assert worst_clean > best_cluttered


def test_clarity_score_is_bounded():
    assert compute_clarity_score(0.0, 1.0) == 0.0
    assert compute_clarity_score(1.0, 0.0) == 100.0
    for focus in (0.0, 0.3, 0.7, 1.0):
        for clutter in (0.0, 0.5, 1.0):
            assert 0.0 <= compute_clarity_score(focus, clutter) <= 100.0


def test_clarity_weights_sum_to_one():
    assert FOCUS_WEIGHT + CLUTTER_WEIGHT == pytest.approx(1.0)


# --- TC-09: focus order ----------------------------------------------------
def test_tc09_focus_order_returns_top5_without_duplicates(model):
    """TC-09: top-5 ranked {x, y, rank} nodes with no duplicate coordinates."""
    img = Image.new("RGB", (1200, 800), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for box in [(80, 60, 220, 130), (520, 300, 700, 380),
                (940, 120, 1120, 210), (200, 600, 380, 700), (760, 620, 900, 720)]:
        d.rectangle(list(box), fill=(12, 12, 12))

    out = predict_saliency(img)
    nodes = extract_focus_order(out.saliency)

    assert len(nodes) == TOP_N_FOCUS_NODES
    coords = [(n.x, n.y) for n in nodes]
    assert len(set(coords)) == len(coords), f"duplicate coordinates: {coords}"

    assert [n.rank for n in nodes] == [1, 2, 3, 4, 5]
    intensities = [n.intensity for n in nodes]
    assert intensities == sorted(intensities, reverse=True)

    h, w = out.saliency.shape
    for n in nodes:
        assert 0 <= n.x < w and 0 <= n.y < h


def test_tc09_nodes_respect_the_suppression_radius(model):
    img = Image.new("RGB", (1000, 700), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for box in [(60, 60, 200, 140), (430, 300, 570, 380), (800, 560, 940, 640)]:
        d.rectangle(list(box), fill=(10, 10, 10))

    out = predict_saliency(img)
    nodes = extract_focus_order(out.saliency)
    radius = nms_radius_for(*out.saliency.shape)

    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            separation = max(abs(a.x - b.x), abs(a.y - b.y))
            assert separation > radius - 1, (
                f"nodes {a.rank} and {b.rank} are {separation}px apart, "
                f"inside the {radius}px suppression radius"
            )


def test_nms_radius_keeps_20px_as_the_floor():
    """The SDS records 20px; it is the floor, scaled up for large canvases."""
    assert nms_radius_for(200, 200) == NMS_RADIUS
    assert nms_radius_for(3000, 1500) > NMS_RADIUS


def test_region_saliency_has_nine_named_cells(model):
    img = Image.new("RGB", (900, 600), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([100, 80, 260, 170], fill=(10, 10, 10))
    out = predict_saliency(img)

    regions = compute_region_saliency(out.saliency)
    assert len(regions) == 9
    assert set(regions) == {
        "top_left", "top_center", "top_right",
        "mid_left", "mid_center", "mid_right",
        "bot_left", "bot_center", "bot_right",
    }
    assert all(0.0 <= v <= 1.0 for v in regions.values())


# --- letterbox alignment ---------------------------------------------------
@pytest.mark.parametrize("width,height", [(1600, 900), (800, 1400), (1000, 1000),
                                          (1920, 620), (500, 1600)])
def test_letterbox_alignment_preserves_dimensions(model, width, height):
    """The heatmap must come back at exactly the input dimensions."""
    img = Image.new("RGB", (width, height), (250, 250, 250))
    ImageDraw.Draw(img).rectangle(
        [int(width * 0.2), int(height * 0.2), int(width * 0.4), int(height * 0.35)],
        fill=(15, 15, 15))

    out = predict_saliency(img)
    assert out.saliency.shape == (height, width)
    assert out.overlay_bgr.shape == (height, width, 3)


def test_letterbox_padding_is_centred():
    img = Image.new("RGB", (1600, 400), (255, 255, 255))
    canvas, meta = letterbox_with_meta(img)

    assert canvas.size == (IMG_SIZE, IMG_SIZE)
    assert meta.orig_width == 1600 and meta.orig_height == 400
    assert meta.pad_left == 0                       # width is the long side
    assert meta.pad_top > 0                         # height is padded
    top, left, bottom, right = meta.crop_box
    assert bottom - top == meta.content_height
    assert right - left == meta.content_width


def test_peak_lands_on_a_known_target(model):
    """A single high-contrast rectangle must attract the top saliency peak."""
    from scipy.ndimage import gaussian_filter

    width, height = 1200, 800
    rect = (820, 250, 940, 330)
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2

    img = Image.new("RGB", (width, height), (255, 255, 255))
    ImageDraw.Draw(img).rectangle(list(rect), fill=(8, 8, 8))

    out = predict_saliency(img)
    smoothed = gaussian_filter(out.saliency, sigma=3.0)
    py, px = np.unravel_index(int(np.argmax(smoothed)), smoothed.shape)

    distance = float(np.hypot(px - cx, py - cy))
    assert distance / float(np.hypot(width, height)) <= 0.15


def test_forward_pass_shape_and_range(model):
    import torch

    img = Image.new("RGB", (IMG_SIZE, IMG_SIZE), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([80, 80, 140, 140], fill=(10, 10, 10))
    canvas, _ = letterbox_with_meta(img)

    with torch.no_grad():
        logits = model(preprocess(canvas).unsqueeze(0))
        saliency = torch.sigmoid(logits).squeeze().cpu().numpy()

    assert tuple(logits.shape) == (1, 1, IMG_SIZE, IMG_SIZE)
    assert saliency.min() >= 0.0 and saliency.max() <= 1.0
    assert saliency.std() > 1e-6


def test_overlay_leaves_cold_regions_legible(model):
    """Alpha falls off with intensity, so near-zero areas stay close to the source."""
    img = Image.new("RGB", (800, 600), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([340, 260, 460, 340], fill=(10, 10, 10))

    saliency = np.zeros((600, 800), dtype=np.float32)
    saliency[260:340, 340:460] = 1.0
    overlay = build_overlay(img, saliency)

    corner = overlay[10, 10]                      # saliency 0 here
    assert np.all(corner > 230), f"cold corner was tinted: {corner}"
    hot = overlay[300, 400]
    assert not np.array_equal(hot, corner)


@pytest.mark.slow
async def test_analytics_surface_through_the_api(client, user, clean_png):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)
    body = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()

    assert 0.0 <= body["clarity_score"] <= 100.0
    assert 0.0 <= body["focus_index"] <= 1.0
    assert 0.0 <= body["clutter_index"] <= 1.0
    assert len(body["region_saliency"]) == 9
    assert len(body["focus_nodes"]) == TOP_N_FOCUS_NODES
