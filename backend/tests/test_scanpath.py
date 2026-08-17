"""Scanpath sequence, timing, and export encoding."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.config import settings
from app.ml.inference import load_model, predict_saliency
from app.services.analytics import (
    SACCADE_MS,
    SCANPATH_NODES,
    TOP_N_FOCUS_NODES,
    analyse,
    dwell_ms_for,
    extract_focus_order,
    scanpath_timeline,
    total_scanpath_ms,
)
from app.services.scanpath import (
    FFmpegUnavailable,
    build_clip,
    encode_gif,
    encode_mp4,
    ffmpeg_path,
    filmstrip,
)
from tests.conftest import upload_and_wait

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
GIF_MAGIC = (b"GIF89a", b"GIF87a")


@pytest.fixture(scope="module")
def model():
    return load_model(settings.MODEL_PATH)


@pytest.fixture(scope="module")
def busy_mockup():
    img = Image.new("RGB", (1000, 700), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for box in [(60, 50, 200, 120), (430, 90, 610, 170), (780, 60, 940, 140),
                (120, 300, 300, 380), (500, 330, 700, 420), (800, 300, 950, 390),
                (100, 560, 280, 650), (450, 550, 640, 640), (760, 570, 930, 660)]:
        d.rectangle(list(box), fill=(15, 15, 15))
    return img


# --- sequence consistency --------------------------------------------------
def test_scanpath_first_five_match_focus_nodes(model, busy_mockup):
    """The animation must never contradict the Focus Order list, and TC-09 must
    keep seeing exactly five nodes."""
    out = predict_saliency(busy_mockup)
    metrics = analyse(out.saliency, np.array(busy_mockup, dtype=np.uint8))

    assert len(metrics.focus_nodes) == TOP_N_FOCUS_NODES
    assert len(metrics.scanpath_nodes) > TOP_N_FOCUS_NODES

    five = [(n.x, n.y, n.rank) for n in metrics.focus_nodes]
    first_five = [(n.x, n.y, n.rank) for n in metrics.scanpath_nodes[:TOP_N_FOCUS_NODES]]
    assert five == first_five


def test_scanpath_extraction_is_deterministic(model, busy_mockup):
    out = predict_saliency(busy_mockup)
    a = extract_focus_order(out.saliency, top_n=SCANPATH_NODES)
    b = extract_focus_order(out.saliency, top_n=SCANPATH_NODES)
    assert [(n.x, n.y) for n in a] == [(n.x, n.y) for n in b]


def test_scanpath_nodes_have_no_duplicate_coordinates(model, busy_mockup):
    out = predict_saliency(busy_mockup)
    nodes = extract_focus_order(out.saliency, top_n=SCANPATH_NODES)
    coords = [(n.x, n.y) for n in nodes]
    assert len(set(coords)) == len(coords)


# --- timing ----------------------------------------------------------------
def test_timeline_is_monotonic_and_gapped_by_saccades(model, busy_mockup):
    out = predict_saliency(busy_mockup)
    nodes = extract_focus_order(out.saliency, top_n=SCANPATH_NODES)
    timeline = scanpath_timeline(nodes)

    assert timeline[0]["start_ms"] == 0
    for step in timeline:
        assert step["end_ms"] == step["start_ms"] + step["dwell_ms"]
    for previous, step in zip(timeline, timeline[1:]):
        assert step["start_ms"] == previous["end_ms"] + SACCADE_MS

    assert total_scanpath_ms(nodes) == timeline[-1]["end_ms"]


def test_dwell_scales_with_predicted_strength():
    assert dwell_ms_for(0.0) < dwell_ms_for(0.5) < dwell_ms_for(1.0)
    # Out-of-range values are clamped, never negative or unbounded.
    assert dwell_ms_for(-3.0) == dwell_ms_for(0.0)
    assert dwell_ms_for(9.0) == dwell_ms_for(1.0)


def test_empty_timeline_is_safe():
    assert scanpath_timeline([]) == []
    assert total_scanpath_ms([]) == 0


# --- rendering -------------------------------------------------------------
@pytest.fixture(scope="module")
def clip(model, busy_mockup):
    out = predict_saliency(busy_mockup)
    metrics = analyse(out.saliency, np.array(busy_mockup, dtype=np.uint8))
    return build_clip(busy_mockup, [n.as_dict() for n in metrics.scanpath_nodes])


def test_clip_dimensions_are_even_for_h264(clip):
    assert clip.width % 2 == 0 and clip.height % 2 == 0
    assert clip.frames, "no frames rendered"
    assert clip.frames[0].shape == (clip.height, clip.width, 3)
    assert clip.frames[0].dtype == np.uint8


def test_clip_frame_count_matches_duration(clip):
    expected = clip.duration_ms // int(1000 / clip.fps)
    assert abs(len(clip.frames) - expected) <= 1


def test_clip_frames_actually_differ(clip):
    """A static clip would mean the gaze marker never moved."""
    first = clip.frames[0]
    middle = clip.frames[len(clip.frames) // 2]
    last = clip.frames[-1]
    assert not np.array_equal(first, middle)
    assert not np.array_equal(middle, last)


def test_build_clip_rejects_an_empty_sequence(busy_mockup):
    with pytest.raises(ValueError):
        build_clip(busy_mockup, [])


def test_gif_encodes_to_valid_bytes(clip):
    data = encode_gif(clip)
    assert data[:6] in GIF_MAGIC
    assert len(data) > 10_000


def test_filmstrip_is_a_png_contact_sheet(clip):
    data = filmstrip(clip, columns=3, rows=2)
    assert data[:8] == PNG_MAGIC
    with Image.open(io.BytesIO(data)) as sheet:
        assert sheet.width == (clip.width // 2) * 3
        assert sheet.height == (clip.height // 2) * 2


def test_mp4_encodes_or_reports_missing_ffmpeg(clip):
    """MP4 needs ffmpeg. Absent, it must raise a typed error the API turns into
    503 rather than a generic failure."""
    if ffmpeg_path() is None:
        with pytest.raises(FFmpegUnavailable):
            encode_mp4(clip)
        pytest.skip("ffmpeg not installed in this environment")

    data = encode_mp4(clip)
    assert data[4:8] == b"ftyp", "not an MP4 container"
    assert len(data) > 5_000


# --- API -------------------------------------------------------------------
@pytest.mark.slow
async def test_result_payload_exposes_the_timeline(client, user, clean_png):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)
    body = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()

    assert len(body["scanpath"]) >= len(body["focus_nodes"])
    assert body["scanpath_total_ms"] > 0
    assert body["scanpath"][0]["start_ms"] == 0
    for step in body["scanpath"]:
        for field in ("rank", "x", "y", "intensity", "start_ms", "dwell_ms", "end_ms"):
            assert field in step

    # The first five steps are the Focus Order nodes, in the same order.
    for node, step in zip(body["focus_nodes"], body["scanpath"]):
        assert (node["x"], node["y"], node["rank"]) == (step["x"], step["y"], step["rank"])


@pytest.mark.slow
async def test_gif_download_endpoint(client, user, clean_png):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)
    resp = await client.get(f"/results/{asset_id}/scanpath.gif", headers=user["headers"])

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/gif"
    assert resp.content[:6] in GIF_MAGIC
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.slow
async def test_mp4_download_endpoint(client, user, clean_png):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)
    resp = await client.get(f"/results/{asset_id}/scanpath.mp4", headers=user["headers"])

    if ffmpeg_path() is None:
        assert resp.status_code == 503
        assert "gif" in resp.json()["detail"].lower()
        return

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content[4:8] == b"ftyp"


@pytest.mark.slow
async def test_scanpath_downloads_are_tenant_isolated(client, user, other_user, clean_png):
    """TC-12 applies to the new endpoints too."""
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)

    for suffix in ("gif", "mp4"):
        resp = await client.get(f"/results/{asset_id}/scanpath.{suffix}",
                                headers=other_user["headers"])
        assert resp.status_code == 403, f"{suffix} leaked to another tenant"


async def test_scanpath_download_requires_auth(client):
    resp = await client.get("/results/whatever/scanpath.gif")
    assert resp.status_code == 401
