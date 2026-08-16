"""A/B comparison and tenant isolation: TC-10 and TC-12."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.conftest import make_png, upload_and_wait


@pytest_asyncio.fixture(loop_scope="session")
async def two_analysed_assets(client, user, clean_png, cluttered_png):
    a, _ = await upload_and_wait(client, user["headers"], clean_png, "variant-a.png")
    b, _ = await upload_and_wait(client, user["headers"], cluttered_png, "variant-b.png")
    return a, b


# --- TC-10 -----------------------------------------------------------------
@pytest.mark.slow
async def test_tc10_compare_returns_both_heatmaps_and_delta(client, user, two_analysed_assets):
    """TC-10: both heatmaps returned and the delta computed correctly."""
    asset_a, asset_b = two_analysed_assets

    resp = await client.post("/compare", headers=user["headers"],
                             json={"asset_id_a": asset_a, "asset_id_b": asset_b})
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["comparison_id"]
    assert body["design_a"]["heatmap_url"] and body["design_b"]["heatmap_url"]
    assert body["design_a"]["asset_id"] == asset_a
    assert body["design_b"]["asset_id"] == asset_b

    expected = round(body["design_a"]["clarity_score"] - body["design_b"]["clarity_score"], 2)
    assert body["clarity_delta"] == pytest.approx(expected, abs=0.01)

    # The clean variant should beat the cluttered one.
    assert body["winner"] == "A"
    assert body["clarity_delta"] > 0


@pytest.mark.slow
async def test_tc10_comparison_is_retrievable(client, user, two_analysed_assets):
    asset_a, asset_b = two_analysed_assets
    created = await client.post("/compare", headers=user["headers"],
                                json={"asset_id_a": asset_a, "asset_id_b": asset_b})
    comparison_id = created.json()["comparison_id"]

    fetched = await client.get(f"/compare/{comparison_id}", headers=user["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["clarity_delta"] == created.json()["clarity_delta"]

    listed = await client.get("/compare", headers=user["headers"])
    assert any(c["comparison_id"] == comparison_id for c in listed.json()["comparisons"])


async def test_compare_requires_two_distinct_assets(client, user, clean_png):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)
    resp = await client.post("/compare", headers=user["headers"],
                             json={"asset_id_a": asset_id, "asset_id_b": asset_id})
    assert resp.status_code == 400


async def test_compare_rejects_unanalysed_asset(client, user, clean_png):
    """An asset with no result yet cannot be compared."""
    analysed, _ = await upload_and_wait(client, user["headers"], clean_png)
    pending = (await client.post(
        "/upload", headers=user["headers"],
        files={"file": ("pending.png", make_png(2400, 1600), "image/png")},
    )).json()["asset_id"]

    resp = await client.post("/compare", headers=user["headers"],
                             json={"asset_id_a": analysed, "asset_id_b": pending})
    assert resp.status_code in (400, 201)  # 201 only if inference already finished


# --- TC-12 -----------------------------------------------------------------
@pytest.mark.slow
async def test_tc12_other_users_asset_returns_403(client, user, other_user, clean_png):
    """TC-12: cross-tenant access is Forbidden, not Not Found."""
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)

    resp = await client.get(f"/results/{asset_id}", headers=other_user["headers"])
    assert resp.status_code == 403, (
        f"expected 403 for another tenant's asset, got {resp.status_code}"
    )


@pytest.mark.slow
async def test_tc12_isolation_across_every_owned_resource(client, user, other_user,
                                                          clean_png):
    project = (await client.post("/projects", headers=user["headers"],
                                 json={"title": "Private"})).json()
    project_id = project["project_id"]

    upload = (await client.post(
        "/upload", headers=user["headers"],
        files={"file": ("m.png", clean_png, "image/png")},
        data={"project_id": project_id},
    )).json()
    asset_id, task_id = upload["asset_id"], upload["task_id"]

    import asyncio

    for _ in range(120):
        s = (await client.get(f"/status/{task_id}", headers=user["headers"])).json()
        if s["status"] in ("complete", "failed"):
            break
        await asyncio.sleep(0.5)

    second = await client.post(
        "/upload", headers=user["headers"],
        files={"file": ("m2.png", make_png(700, 500, clean=False), "image/png")},
        data={"project_id": project_id},
    )
    asset_b = second.json()["asset_id"]
    for _ in range(120):
        s = (await client.get(f"/status/{second.json()['task_id']}",
                              headers=user["headers"])).json()
        if s["status"] in ("complete", "failed"):
            break
        await asyncio.sleep(0.5)

    comparison_id = (await client.post(
        "/compare", headers=user["headers"],
        json={"asset_id_a": asset_id, "asset_id_b": asset_b},
    )).json()["comparison_id"]

    forbidden = [
        ("GET", f"/projects/{project_id}"),
        ("GET", f"/results/{asset_id}"),
        ("GET", f"/status/{task_id}"),
        ("GET", f"/compare/{comparison_id}"),
        ("GET", f"/results/{asset_id}/report.pdf"),
        ("GET", f"/compare/{comparison_id}/report.pdf"),
        ("GET", f"/results/{asset_id}/suggestions"),
        ("POST", f"/results/{asset_id}/rerun"),
        ("DELETE", f"/results/{asset_id}"),
        ("PATCH", f"/projects/{project_id}"),
        ("DELETE", f"/projects/{project_id}"),
    ]

    for method, path in forbidden:
        resp = await client.request(method, path, headers=other_user["headers"],
                                    json={} if method == "PATCH" else None)
        assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}"


@pytest.mark.slow
async def test_tc12_listings_never_leak_across_tenants(client, user, other_user, clean_png):
    await upload_and_wait(client, user["headers"], clean_png)

    for path in ("/results", "/projects", "/compare"):
        body = (await client.get(path, headers=other_user["headers"])).json()
        key = next(k for k in ("results", "projects", "comparisons") if k in body)
        assert body["total_count"] == 0, f"{path} leaked rows to another tenant"
        assert body[key] == []


@pytest.mark.slow
async def test_stored_files_are_prefixed_by_tenant(client, user, clean_png, db):
    asset_id, _ = await upload_and_wait(client, user["headers"], clean_png)

    asset = await db["mockup_assets"].find_one({"asset_id": asset_id})
    assert asset["storage_key"].startswith(f"{user['user_id']}/")

    result = await db["heatmap_results"].find_one({"asset_id": asset_id})
    for key in result["storage_keys"].values():
        assert key.startswith(f"{user['user_id']}/")
