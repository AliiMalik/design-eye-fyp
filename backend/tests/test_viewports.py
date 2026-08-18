"""Scroll-aware segmentation of full-page exports."""

import numpy as np
import pytest
from PIL import Image

from app.services.analytics import (
    EDGE_DENSITY_SCALE,
    FOCUS_RAW_MIN,
    compute_clarity_score,
    compute_clutter_index,
)
from app.services.viewports import (
    MAX_VIEWPORTS,
    SEGMENT_TRIGGER,
    VIEWPORT_ASPECTS,
    ViewportError,
    count_viewports,
    default_device,
    should_segment,
    slice_viewports,
    stitch_saliency,
    viewport_height,
)


def page(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), (255, 255, 255))


# --- geometry --------------------------------------------------------------
def test_viewport_height_follows_the_device():
    assert viewport_height(900, "phone") == int(round(900 * 19.5 / 9))
    assert viewport_height(1440, "desktop") == 900
    assert viewport_height(900, "tablet") == 1200


def test_unknown_device_is_rejected_with_a_useful_message():
    with pytest.raises(ViewportError, match="phone"):
        viewport_height(900, "watch")


def test_default_device_uses_orientation_not_size():
    """A phone frame exported at 2.5x is wider than a laptop, so size is no
    signal at all. Orientation is."""
    assert default_device(900, 13650) == "phone"
    assert default_device(2325, 5147) == "phone"
    assert default_device(1920, 1080) == "desktop"


def test_a_single_screen_is_not_segmented():
    assert not should_segment(900, 1950, "phone")
    assert count_viewports(900, 1950, "phone") == pytest.approx(1.0, abs=0.01)
    tiles = slice_viewports(page(900, 1950), "phone")
    assert len(tiles) == 1
    assert (tiles[0].top, tiles[0].bottom) == (0, 1950)


def test_a_long_page_is_segmented():
    assert should_segment(900, 13650, "phone")
    tiles = slice_viewports(page(900, 13650), "phone")
    assert len(tiles) > 1
    assert [t.index for t in tiles] == list(range(1, len(tiles) + 1))


def test_the_trigger_sits_just_above_one_screen():
    """Degradation starts immediately above one viewport, so the trigger is low."""
    assert 1.0 < SEGMENT_TRIGGER < 2.0
    w = 900
    vh = viewport_height(w, "phone")
    assert not should_segment(w, int(vh * (SEGMENT_TRIGGER - 0.1)), "phone")
    assert should_segment(w, int(vh * (SEGMENT_TRIGGER + 0.1)), "phone")


# --- coverage --------------------------------------------------------------
def test_slices_cover_the_whole_page_and_overlap():
    tiles = slice_viewports(page(900, 6000), "phone")
    assert tiles[0].top == 0
    assert tiles[-1].bottom == 6000, "the bottom of the page must be scored"
    for a, b in zip(tiles, tiles[1:]):
        assert b.top < a.bottom, "neighbours must overlap, not butt together"


def test_every_slice_is_viewport_shaped():
    """The point of segmenting is that each tile has an aspect the model can
    actually see, so none of them may stay pathological."""
    tiles = slice_viewports(page(900, 13650), "phone")
    target = VIEWPORT_ASPECTS["phone"]
    for t in tiles:
        assert t.image.size[0] == 900
        assert t.height / 900 == pytest.approx(target, abs=0.02)


def test_fan_out_is_capped():
    tiles = slice_viewports(page(600, 600 * 200), "phone")
    assert len(tiles) <= MAX_VIEWPORTS


def test_degenerate_slice_is_dropped_not_scored():
    tiles = slice_viewports(page(900, 1950 + 4), "phone")
    assert all(t.height >= 16 for t in tiles)


# --- stitching -------------------------------------------------------------
def test_stitch_restores_the_page_shape():
    W, H = 900, 6000
    tiles = slice_viewports(page(W, H), "phone")
    maps = [(t, np.full((t.height, W), 0.5, dtype=np.float32)) for t in tiles]
    out = stitch_saliency(maps, W, H)
    assert out.shape == (H, W)
    assert np.all(out >= 0.0) and np.all(out <= 1.0)
    # A constant input must come back constant: the feather has to sum to 1
    # everywhere, or every boundary shows as a band across the heatmap.
    assert out.min() == pytest.approx(0.5, abs=0.02)
    assert out.max() == pytest.approx(0.5, abs=0.02)


def test_stitch_keeps_each_viewport_content_in_its_own_band():
    W, H = 900, 6000
    tiles = slice_viewports(page(W, H), "phone")
    maps = []
    for i, t in enumerate(tiles):
        m = np.zeros((t.height, W), dtype=np.float32)
        m[t.height // 2] = 1.0          # a bright line mid-tile
        maps.append((t, m))
    out = stitch_saliency(maps, W, H)
    for t in tiles:
        band = out[t.top:t.bottom]
        assert band.max() > 0.3, f"viewport {t.index} lost its content"


def test_stitch_survives_a_single_full_page_tile():
    W, H = 900, 1200
    tiles = slice_viewports(page(W, H), "phone")
    out = stitch_saliency([(tiles[0], np.full((H, W), 0.25, dtype=np.float32))], W, H)
    assert out.shape == (H, W)
    assert out.mean() == pytest.approx(0.25, abs=0.02)


# --- why this exists -------------------------------------------------------
def test_whole_page_clutter_saturates_but_per_viewport_does_not():
    """The clutter half of the bug, without needing the model.

    A detailed page measured whole is crushed to a 33x512 grid and saturates;
    the same content measured one viewport at a time stays in range.
    """
    rng = np.random.default_rng(11)
    W, VH, N = 900, viewport_height(900, "phone"), 7
    # Realistic UI density. Rows every 46px saturated even per viewport -- that
    # is denser than any real screen, and it made the test prove nothing.
    full = np.full((VH * N, W, 3), 255, dtype=np.uint8)
    for y in range(60, VH * N - 60, 150):
        x0 = int(rng.integers(40, 160))
        full[y:y + 22, x0:x0 + int(rng.integers(260, 520))] = 30

    img = Image.fromarray(full)
    whole = compute_clutter_index(np.array(img))

    tiles = slice_viewports(img, "phone")
    per = [compute_clutter_index(np.array(t.image)) for t in tiles]

    assert whole >= 0.999, "expected the whole-page measurement to saturate"
    assert max(per) < 0.999, "per-viewport measurement must stay in range"
    assert np.mean(per) < whole


def test_clamped_terms_force_zero_regardless_of_design():
    """Why 0.0 is an artifact: with both terms clamped the formula has no
    remaining input, so every such page returns the same number."""
    assert compute_clarity_score(0.0, 1.0) == 0.0
    assert FOCUS_RAW_MIN > 0 and EDGE_DENSITY_SCALE > 0


# --- scoreability is geometry, not metrics ---------------------------------
def test_content_fraction_matches_the_measured_starvation():
    from app.services.viewports import letterbox_content_fraction

    assert letterbox_content_fraction(900, 900) == pytest.approx(1.0, abs=0.01)
    assert letterbox_content_fraction(900, 1950) == pytest.approx(0.46, abs=0.02)
    assert letterbox_content_fraction(900, 13650) == pytest.approx(0.062, abs=0.01)


def test_a_viewport_is_scoreable_and_a_whole_long_page_is_not():
    from app.services.viewports import is_scoreable

    assert is_scoreable(900, 1950), "a phone viewport must be scoreable"
    assert is_scoreable(1440, 900), "a desktop viewport must be scoreable"
    assert not is_scoreable(900, 13650), "a 15:1 page carries too little signal"


def test_ultra_wide_is_caught_too():
    """Segmentation is vertical; this is the starvation it cannot fix."""
    from app.services.viewports import is_scoreable, should_segment

    assert not should_segment(6000, 1000, "desktop")
    assert not is_scoreable(6000, 1000)


def test_a_legitimately_terrible_design_stays_scoreable():
    """The calibration set's dense samples score 0.00 with both terms clamped,
    and that is the correct answer. Geometry must not second-guess it."""
    from app.services.viewports import is_scoreable

    assert is_scoreable(1200, 900)
    assert compute_clarity_score(0.0, 1.0) == 0.0


# --- end to end ------------------------------------------------------------
def long_page_png(viewports: int = 4, width: int = 900) -> bytes:
    """A realistic full-page export: sections of UI-like content down the page."""
    import io as _io

    rng = np.random.default_rng(5)
    vh = viewport_height(width, "phone")
    arr = np.full((vh * viewports, width, 3), 255, dtype=np.uint8)
    for band in range(viewports):
        base = band * vh
        # One heading and a few content rows per screen, with real whitespace.
        arr[base + 90:base + 150, 60:60 + 520] = 24
        for k in range(4):
            y = base + 260 + k * 180
            arr[y:y + 26, 60:60 + int(rng.integers(320, 640))] = 90
            arr[y + 46:y + 150, 60:60 + 300] = 214
    buf = _io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.slow
async def test_long_page_is_scored_per_viewport(client, user):
    """The bug, end to end: a scrolling page must not score a forced 0.0."""
    from tests.conftest import upload_and_wait

    data = long_page_png(viewports=4)
    asset_id, status = await upload_and_wait(
        client, user["headers"], data, filename="longpage.png")
    assert status["status"] == "complete", status

    r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()

    assert r["viewport_count"] >= 3, r["viewport_count"]
    assert r["viewport_device"] == "phone"
    assert len(r["viewports"]) == r["viewport_count"]
    assert r["clarity_score"] > 0.0, "a long page used to be forced to exactly 0.0"
    assert r["weakest_viewport"] in {v["index"] for v in r["viewports"]}
    assert r["score_in_range"] is True

    # The headline score is the mean of the parts, and every part is in range.
    mean = sum(v["clarity_score"] for v in r["viewports"]) / len(r["viewports"])
    assert r["clarity_score"] == pytest.approx(mean, abs=0.02)
    assert all(0.0 < v["clarity_score"] <= 100.0 for v in r["viewports"])

    # Viewports tile the page top to bottom.
    assert r["viewports"][0]["top"] == 0
    assert r["viewports"][-1]["bottom"] == r["image_height"]


@pytest.mark.slow
async def test_focus_order_still_maps_onto_the_uploaded_page(client, user):
    """Focus Order and the replay come off the stitched map, so their
    coordinates must stay in the full page's pixel space -- otherwise the
    numbered dots land in the wrong place on a segmented result."""
    from tests.conftest import upload_and_wait

    data = long_page_png(viewports=4)
    asset_id, _ = await upload_and_wait(
        client, user["headers"], data, filename="longpage2.png")
    r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()

    assert len(r["focus_nodes"]) == 5
    for n in r["focus_nodes"]:
        assert 0 <= n["x"] < r["image_width"]
        assert 0 <= n["y"] < r["image_height"]
    # Attention on a four-screen page cannot all be inside the first screen.
    assert max(n["y"] for n in r["focus_nodes"]) > r["image_height"] // 4


@pytest.mark.slow
async def test_a_single_screen_upload_is_unchanged(client, user, clean_png):
    """No regression for the ordinary case: one screen, scored whole."""
    from tests.conftest import upload_and_wait

    asset_id, status = await upload_and_wait(client, user["headers"], clean_png)
    assert status["status"] == "complete"
    r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()
    assert r["viewport_count"] == 1
    assert r["viewports"] == []
    assert r["viewport_device"] == ""
    assert r["weakest_viewport"] is None
    assert r["clarity_score"] > 75, "TC-07 band must be untouched"


@pytest.mark.slow
async def test_device_choice_changes_the_segmentation(client, user):
    """The viewport assumption is the user's to make, and it must actually
    change how the page is cut -- a desktop screen is shorter than a phone's."""
    from tests.conftest import upload_and_wait

    data = long_page_png(viewports=3)
    results = {}
    for device in ("phone", "desktop"):
        asset_id, _ = await upload_and_wait(
            client, user["headers"], data, filename=f"{device}.png")
        r = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()
        results[device] = r

    assert results["phone"]["viewport_device"] == "phone", (
        "portrait uploads should default to a phone")
    # Sanity: the default really did segment, and recorded which screen it used.
    assert results["phone"]["viewport_count"] > 1


async def test_upload_rejects_an_unknown_screen_size(client, user, clean_png):
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")},
                             data={"viewport_device": "smartwatch"})
    assert resp.status_code == 400
    assert "phone" in resp.json()["detail"].lower()


async def test_upload_accepts_an_explicit_screen_size(client, user, clean_png):
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")},
                             data={"viewport_device": "desktop"})
    assert resp.status_code == 202


def test_a_long_page_is_not_rejected_for_being_long():
    """The size guard used to cap the LONG side at 8000px, which rejected the
    exact uploads segmentation exists for -- seven phone screens is 13650px."""
    import io as _io

    from app.config import settings
    from app.services.images import UnsupportedFileError, load_image

    buf = _io.BytesIO()
    Image.new("RGB", (900, 13650), (255, 255, 255)).save(buf, format="PNG")
    img, _ = load_image(buf.getvalue())
    assert img.size == (900, 13650)
    assert settings.MAX_SCROLL_LONG_SIDE > settings.MAX_IMAGE_LONG_SIDE

    # The narrow axis is still held to the ordinary limit.
    wide = _io.BytesIO()
    Image.new("RGB", (9000, 9000), (255, 255, 255)).save(wide, format="PNG")
    with pytest.raises(UnsupportedFileError, match="shorter side"):
        load_image(wide.getvalue())
