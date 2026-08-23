"""Aspect-aware inference: recovering the resolution a tall frame loses."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.ml.inference import (
    MAX_INFERENCE_TILES,
    MIN_TILED_ASPECT,
    inference_tile_count,
)
from app.services.analytics import (
    compute_clutter_index,
    compute_focus_index,
    normalise_focus,
)
from app.services.viewports import letterbox_content_fraction


def phone_screen(w: int = 720, h: int = 1980) -> Image.Image:
    """A list-style mobile screen: repeated rows, an avatar column, a tab bar."""
    im = Image.new("RGB", (w, h), (253, 245, 243))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 120], fill=(254, 250, 249))
    d.rectangle([int(w * 0.3), 36, int(w * 0.7), 78], fill=(122, 26, 51))
    for i in range(7):
        y = 260 + i * 200
        d.ellipse([42, y, 162, y + 120], fill=(120, 92, 78))
        d.rectangle([200, y + 16, 200 + int(w * 0.4), y + 50], fill=(32, 26, 28))
        d.rectangle([200, y + 74, 200 + int(w * 0.55), y + 98], fill=(150, 140, 142))
    d.rectangle([0, h - 120, w, h], fill=(254, 250, 249))
    return im


def as_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- the geometry decision -------------------------------------------------
def test_near_square_frames_are_not_tiled():
    """The ordinary path must stay untouched -- it is the overwhelming majority
    and it is what the Clarity Score was calibrated on."""
    for w, h in ((1488, 1104), (1200, 900), (1000, 1000), (900, 1200), (900, 1300)):
        assert inference_tile_count(w, h) == 1, f"{w}x{h} should not tile"


def test_tall_frames_are_split_towards_square():
    for w, h, expected in ((720, 1980, 3), (710, 1580, 2), (900, 1950, 2)):
        assert inference_tile_count(w, h) == expected
        # Each band should end up far closer to square than the frame was.
        assert abs((h / expected) / w - 1.0) < abs(h / w - 1.0)


def test_tiling_is_capped():
    assert inference_tile_count(400, 400 * 40) <= MAX_INFERENCE_TILES


def test_threshold_sits_above_every_calibration_sample(sample_paths):
    """A false trigger here would silently move the calibration and invalidate
    TC-07/TC-08, so the gate must clear every sample by a margin."""
    paths = sample_paths["clean"] + sample_paths["cluttered"]
    if not paths:
        pytest.skip("no calibration samples; run scripts/make_samples.py")
    for p in paths:
        with Image.open(p) as im:
            assert inference_tile_count(im.width, im.height) == 1, p.name
            assert im.height / im.width < MIN_TILED_ASPECT


# --- the mechanism ---------------------------------------------------------
def test_a_tall_frame_really_does_starve_the_model():
    """The premise: the square input leaves a tall frame very little of itself."""
    assert letterbox_content_fraction(720, 1980) < 0.40
    assert letterbox_content_fraction(1000, 1000) == pytest.approx(1.0, abs=0.01)
    # Each band of the split gets far more of the input than the whole frame did.
    n = inference_tile_count(720, 1980)
    assert letterbox_content_fraction(720, 1980 // n) > 2 * letterbox_content_fraction(720, 1980)


# --- what it buys ----------------------------------------------------------
@pytest.mark.slow
def test_tiling_recovers_focus_on_a_phone_screen():
    from app.config import settings
    from app.ml.inference import load_model, predict_saliency, predict_saliency_hires

    load_model(settings.MODEL_PATH)
    im = phone_screen()
    before = compute_focus_index(predict_saliency(im).saliency)
    after = compute_focus_index(predict_saliency_hires(im).saliency)
    assert after > before * 1.3, (
        f"expected the split to recover focus: {before:.4f} -> {after:.4f}")


@pytest.mark.slow
def test_calibration_samples_are_bit_identical(sample_paths):
    """The fix must be invisible to everything it was not aimed at."""
    from app.config import settings
    from app.ml.inference import load_model, predict_saliency, predict_saliency_hires

    paths = sample_paths["clean"] + sample_paths["cluttered"]
    if not paths:
        pytest.skip("no calibration samples")
    load_model(settings.MODEL_PATH)
    for p in paths:
        im = Image.open(p).convert("RGB")
        rgb = np.array(im, dtype=np.uint8)
        cl = compute_clutter_index(rgb)
        a = normalise_focus(compute_focus_index(predict_saliency(im).saliency))
        b = normalise_focus(compute_focus_index(predict_saliency_hires(im).saliency))
        assert a == pytest.approx(b, abs=1e-9), f"{p.name} moved: {a} -> {b}"
        assert cl == compute_clutter_index(rgb)


@pytest.mark.slow
def test_stitched_map_keeps_the_frame_shape_and_range():
    from app.config import settings
    from app.ml.inference import load_model, predict_saliency_hires

    load_model(settings.MODEL_PATH)
    im = phone_screen()
    out = predict_saliency_hires(im)
    assert out.saliency.shape == (im.height, im.width)
    assert out.overlay_bgr.shape == (im.height, im.width, 3)
    assert 0.0 <= float(out.saliency.min()) and float(out.saliency.max()) <= 1.0
    # A seam would show as a band of near-zero saliency across the full width.
    rows = out.saliency.mean(axis=1)
    assert rows.min() > 0.0, "a stitch seam blanked a row"


@pytest.mark.slow
async def test_phone_upload_scores_better_end_to_end(client, user):
    from tests.conftest import upload_and_wait

    asset_id, status = await upload_and_wait(
        client, user["headers"], as_png(phone_screen()), filename="phone.png")
    assert status["status"] == "complete"

    r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()
    assert r["viewport_count"] == 1, "1.27 viewports is below the segmentation trigger"
    assert r["clarity_score"] > 20, (
        f"a plain mobile list scored {r['clarity_score']}; uncompensated it was ~15")
    assert len(r["focus_nodes"]) == 5
    assert max(n["y"] for n in r["focus_nodes"]) < r["image_height"]
