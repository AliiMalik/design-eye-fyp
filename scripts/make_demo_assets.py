"""Render the landing-page hero demo from real model output.

The hero shows an actual mockup, its actual predicted heatmap, and its actual
focus nodes -- not an illustration of them.

    python scripts/make_demo_assets.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.ml.inference import load_model, predict_saliency  # noqa: E402
from app.services.analytics import analyse  # noqa: E402

WEIGHTS = ROOT / "backend" / "app" / "ml" / "weights" / "stage3_ui_best_val.pth"
OUT = ROOT / "frontend" / "public" / "demo"
# The metadata is imported as a module, so it lives in the source tree.
# public/ is for statically served files only -- importing JSON out of it
# breaks Turbopack module resolution.
DATA_OUT = ROOT / "frontend" / "lib" / "demo-data.json"
# A real screen reads as a product screenshot; a bare wireframe does not. This
# one is a genuine UI that also scores in the strong band, so the hero shows the
# product working rather than the product complaining.
SOURCE = ROOT / "inputs" / "screens" / "visily-designeye-login.jpg"
CROP_ASPECT = 1.34
MAX_W = 1200

# The hero is a screenshot, so the logo inside it is pixels, not a component --
# left alone it keeps advertising whatever the brand used to be. The old navy
# tile is painted out and the current mark dropped in its place, so the demo
# tracks the brand automatically.
MARK = ROOT / "frontend" / "assets" / "brand" / "mark-compact-light.png"
OLD_MARK_BOX = (716, 183, 772, 240)   # the navy tile in the Visily export
PAINT_BOX = (700, 167, 788, 256)      # the tile plus its drop shadow
CARD_BG = (255, 255, 255)
# The compact mark rather than the full one: the hero renders this screenshot
# at roughly a third of its size, where five rings would be a smudge.
MARK_HEIGHT = 54


def rebrand(img: Image.Image) -> Image.Image:
    if not MARK.is_file():
        raise SystemExit(f"Missing {MARK}. Run scripts/build_brand_assets.py first.")

    tile = np.asarray(img.crop(OLD_MARK_BOX).convert("RGB"), dtype=int)
    if tile.sum(-1).mean() > 400:
        raise SystemExit("OLD_MARK_BOX no longer covers the dark tile -- re-measure it.")

    out = img.convert("RGB").copy()
    out.paste(CARD_BG, PAINT_BOX)

    mark = Image.open(MARK).convert("RGBA")
    w = round(MARK_HEIGHT * mark.width / mark.height)
    mark = mark.resize((w, MARK_HEIGHT), Image.LANCZOS)
    cx = (OLD_MARK_BOX[0] + OLD_MARK_BOX[2]) // 2
    cy = (OLD_MARK_BOX[1] + OLD_MARK_BOX[3]) // 2
    out.paste(mark, (cx - w // 2, cy - MARK_HEIGHT // 2), mark)
    return out


def main() -> int:
    if not SOURCE.is_file():
        print(f"Missing {SOURCE}.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    load_model(WEIGHTS)

    full = rebrand(Image.open(SOURCE))
    crop_h = min(full.height, int(full.width / CROP_ASPECT))
    img = full.crop((0, 0, full.width, crop_h))

    out = predict_saliency(img)
    metrics = analyse(out.saliency, np.array(img, dtype=np.uint8))

    scale = min(1.0, MAX_W / img.width)
    w, h = int(img.width * scale), int(img.height * scale)

    # Hash the filenames: next/image caches aggressively by URL, so a
    # regenerated asset at a stable path keeps serving the stale version.
    for old in OUT.glob("*.png"):
        old.unlink()
    digest = hashlib.sha1(out.saliency.tobytes()).hexdigest()[:8]
    mockup_name = f"mockup.{digest}.png"
    heatmap_name = f"heatmap.{digest}.png"

    img.resize((w, h), Image.LANCZOS).save(OUT / mockup_name, optimize=True)
    cv2.imwrite(str(OUT / heatmap_name), cv2.resize(out.overlay_bgr, (w, h)))

    payload = {
        "width": w,
        "height": h,
        "mockup_src": f"/demo/{mockup_name}",
        "heatmap_src": f"/demo/{heatmap_name}",
        "clarity_score": metrics.clarity_score,
        "focus_index": metrics.focus_index,
        "clutter_index": metrics.clutter_index,
        "region_saliency": metrics.region_saliency,
        "focus_nodes": [
            {**n.as_dict(), "x": round(n.x * scale), "y": round(n.y * scale)}
            for n in metrics.focus_nodes
        ],
    }
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    DATA_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"wrote {OUT}/{mockup_name}, {heatmap_name} and {DATA_OUT}")
    print(f"clarity={metrics.clarity_score} nodes={len(metrics.focus_nodes)} size={w}x{h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
