"""Dark-mode compensation for the saliency checkpoint."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageOps

from app.ml.theme import DARK_UI_LUMA, detect_theme, for_model, is_dark_ui, mean_luminance
from app.services.analytics import compute_edge_density


def sparse_screen(dark: bool, w: int = 738, h: int = 1600) -> Image.Image:
    """One card at the top, a floating button, and a lot of empty space."""
    bg, fg = ((10, 10, 10), (240, 240, 240)) if dark else ((255, 255, 255), (20, 20, 20))
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 220, w - 28, 515], radius=14,
                        fill=(70, 86, 104) if dark else (205, 215, 228))
    d.rectangle([55, 265, 275, 300], fill=fg)
    d.rectangle([55, 395, 175, 415], fill=(150, 150, 150))
    d.rounded_rectangle([w - 123, h - 180, w - 28, h - 85], radius=18, fill=(26, 90, 220))
    return im


def as_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- detection -------------------------------------------------------------
def test_detects_dark_and_light():
    assert is_dark_ui(sparse_screen(dark=True))
    assert not is_dark_ui(sparse_screen(dark=False))
    assert detect_theme(sparse_screen(dark=True)) == "dark"
    assert detect_theme(sparse_screen(dark=False)) == "light"


def test_threshold_clears_every_real_light_screen(sample_paths):
    """A false positive costs a light design ~55 points, so the gate must sit
    well clear of the darkest real light-mode screen (measured at 166.3)."""
    paths = sample_paths["clean"] + sample_paths["cluttered"]
    if not paths:
        pytest.skip("no calibration samples; run scripts/make_samples.py")
    for p in paths:
        luma = mean_luminance(Image.open(p).convert("RGB"))
        assert luma > DARK_UI_LUMA + 40, f"{p.name} at {luma:.0f} is too near the gate"


def test_light_images_are_passed_through_untouched():
    light = sparse_screen(dark=False)
    assert for_model(light, dark=False) is light, "the common path must not copy"


def test_dark_images_are_inverted_for_the_model():
    dark = sparse_screen(dark=True)
    out = for_model(dark, dark=True)
    assert mean_luminance(out) > 255 - mean_luminance(dark) - 5
    assert is_dark_ui(dark) and not is_dark_ui(out)


def test_compensation_preserves_hue():
    """Only luminance flips. Inverting RGB would turn a blue primary button
    orange, which is not the same design in light mode -- and it scored worse
    (79.21 against 79.98) because the model reacts to colour."""
    im = Image.new("RGB", (200, 200), (10, 10, 10))
    ImageDraw.Draw(im).rectangle([40, 40, 160, 120], fill=(26, 90, 220))
    out = np.array(for_model(im, dark=True))
    r, g, b = (int(v) for v in out[80, 100])
    assert b > r, f"the blue button came back as ({r},{g},{b})"
    assert b > g


def test_compensation_does_not_resize_or_reorient():
    """Every coordinate downstream -- focus order, the replay, the region grid --
    is in the original image's pixel space."""
    dark = sparse_screen(dark=True)
    assert for_model(dark, dark=True).size == dark.size


# --- the reason this exists ------------------------------------------------
def test_edge_density_is_invariant_to_inversion():
    """Only the model half is affected. Sobel measures gradient magnitude, so
    the clutter term must be identical -- which is why the observed 38-point
    gap on a real screen was 98% focus."""
    for dark in (True, False):
        im = sparse_screen(dark=dark)
        a = compute_edge_density(np.array(im, dtype=np.uint8))
        b = compute_edge_density(np.array(ImageOps.invert(im), dtype=np.uint8))
        assert a == pytest.approx(b, abs=1e-6)


@pytest.mark.slow
def test_inversion_recovers_focus_on_a_dark_screen():
    """The measurement this module exists for: same layout, colours flipped."""
    from app.config import settings
    from app.ml.inference import load_model, predict_saliency
    from app.services.analytics import compute_focus_index

    load_model(settings.MODEL_PATH)
    dark, light = sparse_screen(True), sparse_screen(False)

    raw_light = compute_focus_index(predict_saliency(light).saliency)
    raw_dark = compute_focus_index(predict_saliency(dark).saliency)
    raw_fixed = compute_focus_index(predict_saliency(for_model(dark, True)).saliency)

    assert raw_dark < raw_light * 0.6, (
        f"expected the checkpoint to under-read dark UI: {raw_dark:.4f} vs {raw_light:.4f}")
    assert raw_fixed > raw_dark * 1.5, (
        f"inversion should recover most of the gap: {raw_dark:.4f} -> {raw_fixed:.4f}")


# --- end to end ------------------------------------------------------------
@pytest.mark.slow
async def test_dark_upload_is_compensated_end_to_end(client, user):
    from tests.conftest import upload_and_wait

    asset_id, status = await upload_and_wait(
        client, user["headers"], as_png(sparse_screen(dark=True)), filename="dark.png")
    assert status["status"] == "complete"

    r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()
    assert r["ui_theme"] == "dark", "the compensation must be recorded, never silent"
    assert r["clarity_score"] > 55, (
        f"a sparse dark screen scored {r['clarity_score']}; uncompensated it was 37.4")


@pytest.mark.slow
async def test_light_upload_is_unaffected(client, user):
    """The regression that would matter most: light screens are the common case."""
    from tests.conftest import upload_and_wait

    asset_id, status = await upload_and_wait(
        client, user["headers"], as_png(sparse_screen(dark=False)), filename="light.png")
    assert status["status"] == "complete"

    r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()
    assert r["ui_theme"] == "light"
    assert r["clarity_score"] > 75, "a clean light screen must stay in the TC-07 band"
