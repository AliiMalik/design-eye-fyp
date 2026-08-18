"""Multi-screen batch upload, fan-out, one-call review, and isolation."""

import asyncio
import io

import pytest
from PIL import Image, ImageDraw

from app.db.mongo import Collections
from app.services.images import MAX_PDF_PAGES, count_pdf_pages, load_pdf_pages
from app.services.llm import (
    FLOW_SUGGESTIONS_PER_SCREEN,
    MAX_SCREENS_PER_CALL,
    FlowPayload,
    _parse_flow,
    generate_flow_suggestions,
)


def make_pdf(pages: int = 4, clean_from: int = 1) -> bytes:
    """A multi-page PDF whose screens differ, so scores are not identical."""
    images = []
    for i in range(pages):
        img = Image.new("RGB", (900, 620), (255, 255, 255))
        d = ImageDraw.Draw(img)
        if i >= clean_from:
            d.rectangle([300, 200, 620, 260], fill=(15, 15, 15))
            d.rectangle([390, 330, 520, 380], fill=(79, 91, 213))
        else:
            for row in range(14):
                for col in range(9):
                    d.rectangle([20 + col * 96, 20 + row * 42,
                                 20 + col * 96 + 80, 20 + row * 42 + 30],
                                fill=(60, 70, 90), outline=(10, 10, 10))
        images.append(img)

    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=96)
    return buf.getvalue()


async def wait_for_batch(client, headers, batch_id: str, timeout_s: int = 300) -> dict:
    for _ in range(timeout_s * 2):
        body = (await client.get(f"/batches/{batch_id}", headers=headers)).json()
        if body["status"] in ("complete", "partial", "failed"):
            return body
        await asyncio.sleep(0.5)
    raise AssertionError("batch did not settle in time")


# --- rasterisation ---------------------------------------------------------
def test_multi_page_pdf_rasterises_every_page():
    data = make_pdf(6)
    assert count_pdf_pages(data) == 6
    pages = load_pdf_pages(data)
    assert len(pages) == 6
    assert all(p.width > 16 and p.height > 16 for p in pages)


def test_page_cap_is_enforced():
    """One upload must not be able to queue unbounded work."""
    data = make_pdf(6)
    assert len(load_pdf_pages(data, limit=3)) == 3
    assert MAX_PDF_PAGES >= 10


def test_count_pdf_pages_is_safe_on_rubbish():
    assert count_pdf_pages(b"definitely not a pdf") == 0


# --- the silent-discard fix ------------------------------------------------
@pytest.mark.slow
async def test_single_upload_reports_extra_pages(client, user):
    """A 6-screen PDF through /upload analyses page 1 -- but must SAY so.

    Before this, the other five screens were dropped with no signal at all.
    """
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("flow.pdf", make_pdf(6), "application/pdf")})
    assert resp.status_code == 202
    body = resp.json()
    assert body["pages_detected"] == 6
    assert body["pages_analysed"] == 1


@pytest.mark.slow
async def test_single_image_upload_reports_one_page(client, user, clean_png):
    resp = await client.post("/upload", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")})
    assert resp.json()["pages_detected"] == 1


# --- fan-out ---------------------------------------------------------------
@pytest.mark.slow
async def test_batch_upload_fans_out_to_one_asset_per_screen(client, user, db):
    resp = await client.post(
        "/upload/batch", headers=user["headers"],
        files={"file": ("checkout.pdf", make_pdf(4), "application/pdf")},
        data={"project_title": "Checkout"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["page_count"] == 4
    assert len(body["task_ids"]) == 4

    assets = await db[Collections.MOCKUP_ASSETS].find(
        {"batch_id": body["batch_id"]}, {"_id": 0}).to_list(length=50)
    assert len(assets) == 4
    assert sorted(a["page_number"] for a in assets) == [1, 2, 3, 4]
    # Each screen is a first-class asset, so results/rerun/scanpath all apply.
    assert all(a["storage_key"].startswith(f"{user['user_id']}/") for a in assets)

    settled = await wait_for_batch(client, user["headers"], body["batch_id"])
    assert settled["status"] == "complete"
    assert settled["screens_complete"] == 4
    assert settled["avg_clarity_score"] is not None
    assert [s["page_number"] for s in settled["screens"]] == [1, 2, 3, 4]


async def test_batch_rejects_a_single_page_pdf(client, user):
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("one.pdf", make_pdf(1), "application/pdf")})
    assert resp.status_code == 400
    assert "only one screen" in resp.json()["detail"].lower()


async def test_batch_rejects_a_non_pdf(client, user, clean_png):
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("m.png", clean_png, "image/png")})
    assert resp.status_code == 400
    assert "pdf" in resp.json()["detail"].lower()


# --- the single batched call ----------------------------------------------
def test_flow_parse_requires_every_screen():
    import json

    reply = json.dumps({
        "flow_summary": "s",
        "screens": [{"screen": 1, "headline": "a", "suggestions": []},
                    {"screen": 2, "headline": "b", "suggestions": []}],
    })
    assert len(_parse_flow(reply, [1, 2]).screens) == 2
    # Rendering 2 of 3 screens would look like a product bug, so it must raise.
    with pytest.raises(ValueError, match="omitted screens"):
        _parse_flow(reply, [1, 2, 3])


async def test_flow_review_uses_exactly_one_provider_call():
    """The whole point: N screens cost ONE call, not N."""
    calls: list[str] = []

    class Counting:
        name = "counting"
        model_name = "counting-1"

        async def generate(self, system: str, user: str) -> str:
            import json

            calls.append(user)
            import re

            wanted = sorted({int(n) for n in re.findall(r'"screen":\s*(\d+)', user)})
            return json.dumps({
                "flow_summary": "clarity falls after screen 2",
                "screens": [
                    {"screen": n, "headline": f"screen {n}",
                     "suggestions": [{"title": "t", "detail": "d",
                                      "severity": "high", "based_on": "clarity_score"}]}
                    for n in wanted
                ],
            })

    screens = [{"screen": i, "clarity_score": 90 - i * 7, "focus_index": 0.5,
                "clutter_index": 0.3, "focus_nodes": [], "region_saliency": {}}
               for i in range(1, 13)]

    payload, status, provider, _ = await generate_flow_suggestions(
        screens, provider=Counting())

    assert status == "ok"
    assert provider == "counting"
    assert len(calls) == 1, f"expected one call for 12 screens, made {len(calls)}"
    assert len(payload.screens) == 12


async def test_long_flow_is_chunked_rather_than_truncated():
    """Beyond the safe ceiling we split, so the count still beats one-per-screen."""
    calls: list[int] = []

    class Chunked:
        name = "chunked"
        model_name = "c"

        async def generate(self, system: str, user: str) -> str:
            import json
            import re

            wanted = sorted({int(n) for n in re.findall(r'"screen":\s*(\d+)', user)})
            calls.append(len(wanted))
            return json.dumps({
                "flow_summary": "part",
                "screens": [{"screen": n, "headline": "h", "suggestions": []}
                            for n in wanted],
            })

    count = MAX_SCREENS_PER_CALL * 2 + 3
    screens = [{"screen": i, "clarity_score": 50, "focus_nodes": [],
                "region_saliency": {}} for i in range(1, count + 1)]

    payload, status, _, _ = await generate_flow_suggestions(screens, provider=Chunked())

    assert status == "ok"
    assert len(payload.screens) == count
    assert len(calls) == 3, f"expected 3 chunks, got {len(calls)}"
    assert max(calls) <= MAX_SCREENS_PER_CALL
    # Still dramatically fewer than one call per screen.
    assert len(calls) < count


async def test_extremes_are_computed_from_our_own_scores():
    """Never trust the model to rank across chunks it did not see together."""
    class Liar:
        name = "liar"
        model_name = "l"

        async def generate(self, system: str, user: str) -> str:
            import json
            import re

            wanted = sorted({int(n) for n in re.findall(r'"screen":\s*(\d+)', user)})
            return json.dumps({
                "flow_summary": "x",
                "weakest_screen": 99, "strongest_screen": 99,
                "screens": [{"screen": n, "headline": "h", "suggestions": []}
                            for n in wanted],
            })

    screens = [
        {"screen": 1, "clarity_score": 80.0, "focus_nodes": [], "region_saliency": {}},
        {"screen": 2, "clarity_score": 12.0, "focus_nodes": [], "region_saliency": {}},
        {"screen": 3, "clarity_score": 95.0, "focus_nodes": [], "region_saliency": {}},
    ]
    payload, status, _, _ = await generate_flow_suggestions(screens, provider=Liar())
    assert status == "ok"
    assert payload.weakest_screen == 2
    assert payload.strongest_screen == 3


async def test_truncated_reply_is_not_blindly_retried():
    """Re-prompting an over-long reply just produces another over-long reply."""
    from app.services.llm import LLMTruncated

    attempts: list[int] = []

    class Truncating:
        name = "trunc"
        model_name = "t"

        async def generate(self, system: str, user: str) -> str:
            attempts.append(1)
            raise LLMTruncated("hit the ceiling")

    screens = [{"screen": 1, "clarity_score": 50, "focus_nodes": [], "region_saliency": {}}]
    payload, status, _, _ = await generate_flow_suggestions(screens, provider=Truncating())

    assert payload is None
    assert status == "error"
    assert len(attempts) == 1, "must not retry a truncated reply"


@pytest.mark.slow
async def test_batch_review_costs_one_quota_unit(client, user, db):
    """A 4-screen batch must consume 1 of the daily allowance, not 4."""
    from datetime import datetime, timezone

    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("f.pdf", make_pdf(4), "application/pdf")})
    batch_id = resp.json()["batch_id"]
    await wait_for_batch(client, user["headers"], batch_id)

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    before = await db[Collections.LLM_USAGE].find_one(
        {"user_id": user["user_id"], "day": day}) or {"count": 0}

    review = await client.post(f"/batches/{batch_id}/suggestions",
                               headers=user["headers"], json={"regenerate": True})
    assert review.status_code == 200

    after = await db[Collections.LLM_USAGE].find_one(
        {"user_id": user["user_id"], "day": day}) or {"count": 0}
    assert int(after["count"]) - int(before.get("count", 0)) == 1


@pytest.mark.slow
async def test_batch_review_fans_out_to_per_screen_documents(client, user):
    """The one reply must populate the existing per-screen endpoint."""
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("f.pdf", make_pdf(3), "application/pdf")})
    batch_id = resp.json()["batch_id"]
    await wait_for_batch(client, user["headers"], batch_id)

    reviewed = (await client.post(f"/batches/{batch_id}/suggestions",
                                  headers=user["headers"],
                                  json={"regenerate": True})).json()
    assert reviewed["llm_status"] == "ok"
    assert reviewed["flow_summary"]

    for screen in reviewed["screens"]:
        assert screen["suggestions"], f"screen {screen['page_number']} got nothing"
        # GET /results/{id}/suggestions must work unchanged for a batch screen.
        per = await client.get(f"/results/{screen['asset_id']}/suggestions",
                               headers=user["headers"])
        assert per.status_code == 200
        assert per.json()["llm_status"] == "ok"
        assert len(per.json()["suggestions"]) == len(screen["suggestions"])


# --- isolation and reports -------------------------------------------------
@pytest.mark.slow
async def test_batches_are_tenant_isolated(client, user, other_user):
    """TC-12 extends to every batch route."""
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("f.pdf", make_pdf(3), "application/pdf")})
    batch_id = resp.json()["batch_id"]

    for method, path in [
        ("GET", f"/batches/{batch_id}"),
        ("GET", f"/batches/{batch_id}/report.pdf"),
        ("POST", f"/batches/{batch_id}/suggestions"),
        ("DELETE", f"/batches/{batch_id}"),
    ]:
        r = await client.request(method, path, headers=other_user["headers"],
                                 json={} if method == "POST" else None)
        assert r.status_code == 403, f"{method} {path} returned {r.status_code}"

    listed = await client.get("/batches", headers=other_user["headers"])
    assert listed.json()["total_count"] == 0


async def test_batch_routes_require_auth(client):
    assert (await client.get("/batches")).status_code == 401
    assert (await client.get("/batches/anything")).status_code == 401


@pytest.mark.slow
async def test_flow_report_pdf(client, user):
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("f.pdf", make_pdf(3), "application/pdf")})
    batch_id = resp.json()["batch_id"]
    await wait_for_batch(client, user["headers"], batch_id)

    pdf = await client.get(f"/batches/{batch_id}/report.pdf", headers=user["headers"])
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    # Embedded images are downscaled first; a full-resolution embed produced a
    # 21MB report for eight screens.
    assert len(pdf.content) < 8 * 1024 * 1024, f"report too large: {len(pdf.content)}"


@pytest.mark.slow
async def test_deleting_a_batch_removes_every_screen(client, user, db):
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("f.pdf", make_pdf(3), "application/pdf")})
    batch_id = resp.json()["batch_id"]
    await wait_for_batch(client, user["headers"], batch_id)

    assert (await client.delete(f"/batches/{batch_id}",
                                headers=user["headers"])).status_code == 200
    assert (await client.get(f"/batches/{batch_id}",
                             headers=user["headers"])).status_code == 404
    assert await db[Collections.MOCKUP_ASSETS].count_documents({"batch_id": batch_id}) == 0


def test_flow_defaults_are_sane():
    assert FLOW_SUGGESTIONS_PER_SCREEN >= 1
    assert MAX_SCREENS_PER_CALL >= 10
    assert FlowPayload().screens == []


# --- plain language --------------------------------------------------------
JARGON = ["clutter_index", "focus_index", "region_saliency", "focus_nodes",
          "clarity_score", "saliency", "intensity", "edge density", "3x3"]


def test_prompts_forbid_internal_field_names_in_prose():
    """The designer reading a suggestion has never seen our field names."""
    from app.services.llm_prompts import (
        FLOW_SYSTEM_PROMPT,
        PLAIN_LANGUAGE_RULES,
        SYSTEM_PROMPT,
    )

    assert "NEVER print an internal field name" in PLAIN_LANGUAGE_RULES
    assert PLAIN_LANGUAGE_RULES in SYSTEM_PROMPT
    flow = (FLOW_SYSTEM_PROMPT.replace("{per_screen}", "2")
            .replace("{plain_language}", PLAIN_LANGUAGE_RULES))
    assert PLAIN_LANGUAGE_RULES in flow
    # based_on is machine-read, so the schema must still name the metrics.
    assert '"based_on"' in SYSTEM_PROMPT


async def test_mock_suggestions_read_as_english():
    """Mock is the default, so its copy is what most people actually see."""
    import json

    from app.services.llm import MockProvider
    from app.services.llm_prompts import build_flow_prompt, build_user_prompt

    single = json.loads(await MockProvider().generate(
        "", build_user_prompt({"clarity_score": 43.45})))
    prose = " ".join(
        [single["summary"]]
        + [s["title"] + " " + s["detail"] for s in single["suggestions"]]
    ).lower()
    for term in JARGON:
        assert term not in prose, f"single-screen copy leaks {term!r}"

    screens = [{"screen": i, "clarity_score": 90 - i * 9,
                "focus_nodes": [], "region_saliency": {}} for i in range(1, 4)]
    flow = json.loads(await MockProvider().generate(
        "", build_flow_prompt(screens, 2)))
    flow_prose = " ".join(
        [flow["flow_summary"]]
        + [s["headline"] for s in flow["screens"]]
        + [i["title"] + " " + i["detail"]
           for s in flow["screens"] for i in s["suggestions"]]
    ).lower()
    for term in JARGON:
        assert term not in flow_prose, f"flow copy leaks {term!r}"


@pytest.mark.slow
async def test_batch_list_reports_derived_status(client, user):
    """The list read the stored field and showed finished flows as processing."""
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("f.pdf", make_pdf(3), "application/pdf")})
    batch_id = resp.json()["batch_id"]
    await wait_for_batch(client, user["headers"], batch_id)

    listed = (await client.get("/batches", headers=user["headers"])).json()
    row = next(b for b in listed["batches"] if b["batch_id"] == batch_id)
    assert row["status"] == "complete", "list disagrees with the batch detail view"
    assert row["avg_clarity_score"] is not None
    assert row["page_count"] == 3


def test_status_derivation_covers_every_mix():
    from app.api.v1.batches import _derive_status

    assert _derive_status(0, 0, 0) == "processing"
    assert _derive_status(3, 3, 0) == "complete"
    assert _derive_status(3, 0, 3) == "failed"
    assert _derive_status(3, 2, 1) == "partial"
    assert _derive_status(3, 1, 0) == "processing"


def test_pdf_labels_the_metric_basis():
    """The report is client-facing; a raw field name has no place in it."""
    from app.services.pdf import _basis

    assert _basis({"based_on": "clutter_index"}) == "Clutter index"
    assert _basis({"based_on": "clarity_score"}) == "Clarity Score"
    # An unknown value must still render as words, never as snake_case.
    assert "_" not in _basis({"based_on": "some_new_metric"})
    assert _basis({}) == ""


# --- size ceilings ---------------------------------------------------------
def test_pdf_gets_a_larger_ceiling_than_an_image():
    """A real multi-screen export is routinely bigger than any one mockup."""
    from app.config import settings
    from app.models.domain import AssetFormat
    from app.services.images import UnsupportedFileError, size_limit_mb, validate_size

    assert settings.MAX_PDF_UPLOAD_MB > settings.MAX_UPLOAD_MB
    assert size_limit_mb(AssetFormat.PDF) == settings.MAX_PDF_UPLOAD_MB
    assert size_limit_mb(AssetFormat.PNG) == settings.MAX_UPLOAD_MB
    assert size_limit_mb(None) == settings.MAX_UPLOAD_MB

    # Between the two ceilings: fine as a PDF, refused as an image.
    between = b"x" * ((settings.MAX_UPLOAD_MB + 1) * 1024 * 1024)
    validate_size(between, AssetFormat.PDF)
    with pytest.raises(UnsupportedFileError, match=str(settings.MAX_UPLOAD_MB)):
        validate_size(between, AssetFormat.PNG)

    too_big = b"x" * ((settings.MAX_PDF_UPLOAD_MB + 1) * 1024 * 1024)
    with pytest.raises(UnsupportedFileError, match=str(settings.MAX_PDF_UPLOAD_MB)):
        validate_size(too_big, AssetFormat.PDF)


@pytest.mark.slow
async def test_batch_accepts_a_pdf_over_the_image_ceiling(client, user):
    """The whole point of the raise: a real Figma export gets through."""
    from app.config import settings

    pdf = make_pdf(4)
    # Pad past the image ceiling without disturbing the PDF structure: trailing
    # bytes after %%EOF are ignored by every reader.
    padding = (settings.MAX_UPLOAD_MB + 2) * 1024 * 1024 - len(pdf)
    fat = pdf + b"\n% " + b"0" * max(0, padding)
    assert len(fat) > settings.MAX_UPLOAD_MB * 1024 * 1024
    assert len(fat) < settings.MAX_PDF_UPLOAD_MB * 1024 * 1024

    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("big-flow.pdf", fat, "application/pdf")})
    assert resp.status_code == 202, resp.text
    assert resp.json()["page_count"] == 4


@pytest.mark.slow
async def test_batch_rejects_a_pdf_over_the_pdf_ceiling(client, user):
    from app.config import settings

    pdf = make_pdf(2)
    fat = pdf + b"\n% " + b"0" * ((settings.MAX_PDF_UPLOAD_MB + 1) * 1024 * 1024)
    resp = await client.post("/upload/batch", headers=user["headers"],
                             files={"file": ("huge.pdf", fat, "application/pdf")})
    assert resp.status_code == 400
    assert str(settings.MAX_PDF_UPLOAD_MB) in resp.json()["detail"]
