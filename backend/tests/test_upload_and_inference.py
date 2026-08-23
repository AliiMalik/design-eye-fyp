"""Upload, validation, and inference test cases: TC-03, TC-04, TC-05, TC-06, TC-13."""

from __future__ import annotations

import io
import time

import pytest
from PIL import Image

from tests.conftest import make_png, upload_and_wait


async def test_tc03_upload_valid_mockup(client, user, clean_png):
    """TC-03: file stored, metadata created, task_id returned with status pending."""
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("hero.png", clean_png, "image/png")})

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["asset_id"] and body["task_id"]
    assert body["status"] == "pending"

    listed = await client.get("/results", headers=user["headers"])
    assert any(r["asset_id"] == body["asset_id"] for r in listed.json()["results"])


async def test_tc04_unsupported_format_rejected(client, user):
    """TC-04 (adapted): raster formats are now accepted, so a genuinely
    unsupported type is used. See docs/DEVIATIONS.md."""
    resp = await client.post(
        "/upload", headers=user["headers"],
        files={"file": ("notes.txt", b"this is plain text, not an image", "text/plain")},
    )
    assert resp.status_code == 400
    assert "invalid file format" in resp.json()["detail"].lower()


async def test_tc04_extension_is_not_trusted(client, user):
    """A text file renamed to .png must still be rejected: content is sniffed."""
    resp = await client.post(
        "/upload", headers=user["headers"],
        files={"file": ("disguised.png", b"not really a png at all", "image/png")},
    )
    assert resp.status_code == 400


async def test_tc04_raster_formats_are_accepted(client, user):
    """The documented override: PNG/JPEG/WEBP are valid inputs."""
    img = Image.new("RGB", (400, 300), (250, 250, 250))
    for fmt, name, mime in (("JPEG", "m.jpg", "image/jpeg"), ("WEBP", "m.webp", "image/webp")):
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        resp = await client.post("/upload", headers=user["headers"],
                                 files={"file": (name, buf.getvalue(), mime)})
        assert resp.status_code == 202, f"{fmt}: {resp.text}"


async def test_tc05_oversize_file_rejected(client, user):
    """TC-05: an image above the ceiling is refused.

    Derived from settings rather than hardcoded, so raising a limit cannot
    silently turn this into a test that asserts nothing.
    """
    from app.config import settings

    over = settings.MAX_UPLOAD_MB * 1024 * 1024 + 1024
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * over
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("huge.png", oversized, "image/png")})
    assert resp.status_code == 400
    assert f"{settings.MAX_UPLOAD_MB}mb" in resp.json()["detail"].lower()


async def test_empty_file_rejected(client, user):
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("empty.png", b"", "image/png")})
    assert resp.status_code == 400


@pytest.mark.slow
async def test_tc06_inference_completes_within_sla(client, user, clean_png):
    """TC-06: the task reaches 'complete' and the result is persisted."""
    started = time.perf_counter()
    asset_id, status = await upload_and_wait(client, user["headers"], clean_png)
    elapsed = time.perf_counter() - started

    assert status["status"] == "complete", status
    assert status["clarity_score"] is not None
    assert elapsed < 30, f"exceeded the 30s SLA: {elapsed:.1f}s"

    result = await client.get(f"/results/{asset_id}", headers=user["headers"])
    assert result.status_code == 200
    body = result.json()
    assert body["heatmap_url"] and body["saliency_array_url"]
    assert body["model_version"]
    assert body["inference_time_ms"] > 0


@pytest.mark.slow
async def test_status_reports_stage_progression(client, user, clean_png):
    asset_id, status = await upload_and_wait(client, user["headers"], clean_png)
    assert status["stage"] == "complete"
    assert status["asset_id"] == asset_id
    assert status["completed_at"] is not None


@pytest.mark.slow
async def test_tc13_rerun_without_reupload(client, user, clean_png):
    """TC-13: a stored asset is re-analysed from its saved file."""
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)

    before = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()

    rerun = await client.post(f"/results/{asset_id}/rerun", headers=user["headers"])
    assert rerun.status_code == 200
    new_task = rerun.json()["new_task_id"]
    assert rerun.json()["status"] == "pending"

    import asyncio

    for _ in range(120):
        status = (await client.get(f"/status/{new_task}", headers=user["headers"])).json()
        if status["status"] in ("complete", "failed"):
            break
        await asyncio.sleep(0.5)
    assert status["status"] == "complete"

    after = (await client.get(f"/results/{asset_id}", headers=user["headers"])).json()
    # Deterministic model: rerunning the same pixels reproduces the same score.
    assert after["clarity_score"] == pytest.approx(before["clarity_score"], abs=0.01)
    assert after["result_id"] != before["result_id"]


async def test_upload_creates_default_project_when_none_given(client, user, clean_png):
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")})
    assert resp.status_code == 202

    projects = (await client.get("/projects", headers=user["headers"])).json()
    assert any(p["title"] == "My Uploads" for p in projects["projects"])


async def test_upload_into_explicit_project(client, user, clean_png):
    created = await client.post("/projects", headers=user["headers"],
                                json={"title": "Explicit", "description": "d"})
    project_id = created.json()["project_id"]

    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")},
                             data={"project_id": project_id})
    assert resp.status_code == 202

    detail = await client.get(f"/projects/{project_id}", headers=user["headers"])
    assert len(detail.json()["assets"]) == 1


@pytest.mark.slow
async def test_delete_removes_asset_and_result(client, user, clean_png):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)

    deleted = await client.delete(f"/results/{asset_id}", headers=user["headers"])
    assert deleted.status_code == 200

    assert (await client.get(f"/results/{asset_id}",
                             headers=user["headers"])).status_code == 404


# --- project grouping (the Chrome extension's path) ------------------------
@pytest.mark.slow
async def test_project_title_groups_captures_by_site(client, user, clean_png, db):
    """The extension sends the captured site's hostname, so repeat captures of
    one site collect in one project instead of scattering."""
    from app.db.mongo import Collections

    for _ in range(2):
        resp = await client.post("/upload", headers=user["headers"],
                                 files={"file": ("a.png", clean_png, "image/png")},
                                 data={"project_title": "dribbble.com"})
        assert resp.status_code == 202, resp.text

    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("b.png", clean_png, "image/png")},
                             data={"project_title": "figma.com"})
    assert resp.status_code == 202

    titles = await db[Collections.PROJECTS].distinct(
        "title", {"user_id": user["user_id"]})
    assert "dribbble.com" in titles and "figma.com" in titles

    projects = await db[Collections.PROJECTS].find(
        {"user_id": user["user_id"], "title": "dribbble.com"}).to_list(length=10)
    assert len(projects) == 1, "a second capture must reuse the project, not add one"

    assets = await db[Collections.MOCKUP_ASSETS].count_documents(
        {"project_id": projects[0]["project_id"]})
    assert assets == 2


@pytest.mark.slow
async def test_upload_without_a_title_still_uses_the_default_project(
    client, user, clean_png, db,
):
    """The existing contract is untouched when no title is sent."""
    from app.db.mongo import Collections

    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")})
    assert resp.status_code == 202
    titles = await db[Collections.PROJECTS].distinct(
        "title", {"user_id": user["user_id"]})
    assert "My Uploads" in titles


@pytest.mark.slow
async def test_project_titles_are_per_user(client, user, other_user, clean_png, db):
    """Two people capturing the same site must not share a project."""
    from app.db.mongo import Collections

    import uuid

    # A unique title per run: the test database is not reset between runs, so a
    # fixed one accumulated owners from earlier runs and the count drifted.
    # Scoping to the two accounts under test is the real property anyway.
    site = f"stripe-{uuid.uuid4().hex[:8]}.com"

    for who in (user, other_user):
        resp = await client.post("/upload", headers=who["headers"],
                                 files={"file": ("s.png", clean_png, "image/png")},
                                 data={"project_title": site})
        assert resp.status_code == 202

    mine = await db[Collections.PROJECTS].find(
        {"title": site, "user_id": user["user_id"]}).to_list(length=10)
    theirs = await db[Collections.PROJECTS].find(
        {"title": site, "user_id": other_user["user_id"]}).to_list(length=10)

    assert len(mine) == 1 and len(theirs) == 1, "each account gets exactly one"
    assert mine[0]["project_id"] != theirs[0]["project_id"], (
        "the project must not be shared across accounts")
