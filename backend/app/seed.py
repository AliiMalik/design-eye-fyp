"""Seed the demo account so the FYP presentation opens on a populated dashboard.

Creates demo@designeye.app / Demo@1234 with two projects and several fully
analysed mockups drawn from inputs/samples/ (falling back to the Visily screens).

    python -m app.seed              # add missing data, keep what exists
    python -m app.seed --reset      # wipe the demo user first

Also reachable from the repo root as scripts/seed_demo.py.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Resolve the repo root whether running from the source tree or from /app
# inside the container (where scripts/ and inputs/ may not exist).
ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "inputs").is_dir() and Path("/inputs").is_dir():
    # In the container the repo's inputs/ is bind-mounted at /inputs.
    ROOT = Path("/")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.indexes import ensure_indexes  # noqa: E402
from app.db.mongo import Collections, connect_to_mongo, close_mongo_connection  # noqa: E402
from app.ml.inference import load_model, predict_saliency  # noqa: E402
from app.models.domain import (  # noqa: E402
    ABComparison,
    AssetFormat,
    AssetStatus,
    HeatmapResult,
    InferenceTask,
    MockupAsset,
    Project,
    TaskStatus,
    User,
    UserRole,
    new_id,
    utcnow,
)
from app.services.analytics import analyse  # noqa: E402
from app.services.images import encode_png  # noqa: E402
from app.services.storage import get_storage  # noqa: E402

from PIL import ImageDraw  # noqa: E402

DEMO_EMAIL = "demo@designeye.app"
DEMO_PASSWORD = "Demo@1234"
DEMO_NAME = "Demo Designer"

def _generate(kind: str, seed: int) -> Image.Image:
    """Fallback mockup when inputs/ is not present (e.g. inside the container).

    BUILD.md section 11 allows generated placeholders when no samples exist.
    """
    import random

    W, H = 1440, 900
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)

    if kind == "clean":
        # Vary the layout by seed, or every clean placeholder renders the same
        # image and the demo dashboard shows three identical mockups.
        cx = rng.choice([620, 720, 820])
        top = rng.choice([200, 250, 300])
        width = rng.choice([480, 600, 700])
        d.rectangle([720 - width // 2, top, 720 + width // 2, top + 52], fill=(17, 24, 39))
        d.rectangle([760 - width // 3, top + 74, 680 + width // 3, top + 106],
                    fill=(148, 163, 184))
        d.rectangle([cx - 100, top + 180, cx + 100, top + 232], fill=(79, 91, 213))
        if rng.random() > 0.5:
            d.rounded_rectangle([200, H - 260, 1240, H - 90], radius=24,
                                outline=(226, 232, 240), width=3)
    else:
        for _ in range(280):
            x, y = rng.randint(0, W - 60), rng.randint(0, H - 50)
            d.rectangle([x, y, x + rng.randint(24, 140), y + rng.randint(16, 60)],
                        fill=(rng.randint(0, 220), rng.randint(0, 220), rng.randint(0, 220)),
                        outline=(15, 23, 42), width=2)
    return img


SEED_PLAN = [
    ("Landing Page Experiments", "Hero and CTA variants under attention review", [
        ("inputs/samples/clean/real_login.png", "login-screen-v2.png", "clean"),
        ("inputs/samples/clean/synth_hero.png", "hero-minimal-v1.png", "clean"),
        ("inputs/samples/cluttered/synth_ad_heavy.png", "hero-promo-heavy-v1.png", "cluttered"),
    ]),
    ("Dashboard Redesign", "Internal analytics dashboard clarity audit", [
        ("inputs/screens/visily-designeye-designer-dashboard.jpg", "dashboard-overview.png", "clean"),
        ("inputs/samples/cluttered/synth_dense_dashboard.png", "dashboard-dense-v0.png", "cluttered"),
    ]),
]


async def _wipe(db, user_id: str) -> None:
    for coll in (
        Collections.HEATMAP_RESULTS, Collections.MOCKUP_ASSETS, Collections.PROJECTS,
        Collections.INFERENCE_TASKS, Collections.AB_COMPARISONS,
        Collections.SUGGESTIONS, Collections.LLM_USAGE,
    ):
        await db[coll].delete_many({"user_id": user_id})


async def seed(reset: bool) -> int:
    db = await connect_to_mongo()
    await ensure_indexes(db)
    storage = get_storage()
    load_model(settings.MODEL_PATH)

    user = await db[Collections.USERS].find_one({"email": DEMO_EMAIL}, {"_id": 0})
    if user is None:
        doc = User(
            email=DEMO_EMAIL, display_name=DEMO_NAME,
            password_hash=hash_password(DEMO_PASSWORD), role=UserRole.DESIGNER,
            bio="Product designer using DesignEye to validate hierarchy before launch.",
        )
        doc.tenant_prefix = doc.user_id
        user = doc.to_mongo()
        await db[Collections.USERS].insert_one(dict(user))
        print(f"created user {DEMO_EMAIL}")
    else:
        print(f"user {DEMO_EMAIL} already exists")

    user_id = user["user_id"]

    if reset:
        await _wipe(db, user_id)
        print("wiped existing demo content")

    existing = await db[Collections.MOCKUP_ASSETS].count_documents({"user_id": user_id})
    if existing and not reset:
        print(f"{existing} assets already seeded; nothing to do. Use --reset to rebuild.")
        await close_mongo_connection()
        return 0

    analysed_ids: list[str] = []

    for title, description, files in SEED_PLAN:
        project = Project(user_id=user_id, title=title, description=description)
        await db[Collections.PROJECTS].insert_one(dict(project.to_mongo()))
        print(f"\nproject: {title}")

        for index, (rel_path, filename, kind) in enumerate(files):
            source = ROOT / rel_path
            if source.is_file():
                img = Image.open(source).convert("RGB")
                size_kb = max(1, source.stat().st_size // 1024)
            else:
                img = _generate(kind, seed=hash(filename) % 10_000)
                size_kb = 120
                print(f"  (generated placeholder for {filename})")
            asset = MockupAsset(
                project_id=project.project_id, user_id=user_id, file_url="",
                storage_key="", original_filename=filename, format=AssetFormat.PNG,
                file_size_kb=size_kb,
                width=img.width, height=img.height, status=AssetStatus.COMPLETE,
            )
            upload_key = storage.tenant_key(user_id, "uploads", f"{asset.asset_id}.png")
            asset.file_url = storage.save_bytes(upload_key, encode_png(img), "image/png")
            asset.storage_key = upload_key
            await db[Collections.MOCKUP_ASSETS].insert_one(dict(asset.to_mongo()))

            out = predict_saliency(img)
            metrics = analyse(out.saliency, np.array(img, dtype=np.uint8))

            overlay_key = storage.tenant_key(user_id, "results", f"{asset.asset_id}_heatmap.png")
            saliency_key = storage.tenant_key(user_id, "results", f"{asset.asset_id}_saliency.npy")
            import cv2

            ok, buf = cv2.imencode(".png", out.overlay_bgr)
            if not ok:
                print(f"  failed to encode overlay for {filename}")
                continue

            heatmap_url = storage.save_bytes(overlay_key, buf.tobytes(), "image/png")
            saliency_url = storage.save_npy(saliency_key, out.saliency)

            result = HeatmapResult(
                result_id=new_id(), asset_id=asset.asset_id, user_id=user_id,
                heatmap_url=heatmap_url, saliency_array_url=saliency_url,
                clarity_score=metrics.clarity_score, focus_index=metrics.focus_index,
                clutter_index=metrics.clutter_index,
                region_saliency=metrics.region_saliency,
                focus_nodes=[n.as_dict() for n in metrics.focus_nodes],
                scanpath_nodes=[n.as_dict() for n in metrics.scanpath_nodes],
                model_version=settings.MODEL_VERSION,
                inference_time_ms=out.inference_time_ms,
            )
            doc = result.to_mongo()
            doc["storage_keys"] = {"heatmap": overlay_key, "saliency": saliency_key}
            await db[Collections.HEATMAP_RESULTS].replace_one(
                {"asset_id": asset.asset_id}, doc, upsert=True)

            task = InferenceTask(
                asset_id=asset.asset_id, user_id=user_id,
                status=TaskStatus.COMPLETE, stage="complete", completed_at=utcnow(),
            )
            await db[Collections.INFERENCE_TASKS].insert_one(dict(task.to_mongo()))

            analysed_ids.append(asset.asset_id)
            print(f"  {filename:<30} clarity={metrics.clarity_score:6.2f} "
                  f"({out.inference_time_ms} ms)")

    # One ready-made A/B comparison so the compare screen opens populated.
    if len(analysed_ids) >= 2:
        a, b = analysed_ids[0], analysed_ids[-1]
        ra = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": a}, {"_id": 0})
        rb = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": b}, {"_id": 0})
        delta = round(float(ra["clarity_score"]) - float(rb["clarity_score"]), 2)
        comparison = ABComparison(
            user_id=user_id, asset_id_a=a, asset_id_b=b, clarity_delta=delta)
        await db[Collections.AB_COMPARISONS].insert_one(dict(comparison.to_mongo()))
        print(f"\ncomparison seeded: delta {delta:+.2f}")

    print(f"\nSeed complete. Sign in with {DEMO_EMAIL} / {DEMO_PASSWORD}")
    await close_mongo_connection()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="delete the demo user's existing content first")
    args = parser.parse_args()
    return asyncio.run(seed(args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
