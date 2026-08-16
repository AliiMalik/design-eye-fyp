"""Self-verification for the saliency inference path (BUILD.md section 3).

Run this BEFORE building anything on top of the model. If any check fails, the
preprocessing or the checkpoint is wrong and downstream results are meaningless.

    python scripts/verify_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from scipy.ndimage import gaussian_filter  # noqa: E402

from app.ml.inference import get_model_meta, load_model, predict_saliency  # noqa: E402
from app.ml.model import SalGANGenerator  # noqa: E402
from app.ml.preprocess import IMG_SIZE, letterbox_with_meta, preprocess  # noqa: E402

WEIGHTS = BACKEND / "app" / "ml" / "weights" / "stage3_ui_best_val.pth"
PEAK_TOLERANCE = 0.15  # fraction of image diagonal

_failures: list[str] = []
_passes: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (_passes if ok else _failures).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    return ok


def test_strict_load() -> None:
    print("\n[1/4] Checkpoint loads with strict=True")
    ckpt = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    state = ckpt["G"] if isinstance(ckpt, dict) and "G" in ckpt else ckpt

    model = SalGANGenerator(pretrained=False)
    incompatible = model.load_state_dict(state, strict=False)
    check("zero missing keys", not incompatible.missing_keys,
          str(list(incompatible.missing_keys)[:5]) if incompatible.missing_keys else "")
    check("zero unexpected keys", not incompatible.unexpected_keys,
          str(list(incompatible.unexpected_keys)[:5]) if incompatible.unexpected_keys else "")

    try:
        model.load_state_dict(state, strict=True)
        check("load_state_dict(strict=True) succeeds", True)
    except RuntimeError as exc:
        check("load_state_dict(strict=True) succeeds", False, str(exc)[:200])

    if isinstance(ckpt, dict):
        print(f"       checkpoint metadata: epoch={ckpt.get('epoch')} val={ckpt.get('val')}")


def test_forward_pass() -> None:
    print("\n[2/4] Forward pass shape and value range")
    model = load_model(WEIGHTS)
    print(f"       loaded meta: {get_model_meta().get('checkpoint_model_version')} "
          f"epoch={get_model_meta().get('epoch')}")

    img = Image.new("RGB", (IMG_SIZE, IMG_SIZE), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([80, 80, 140, 140], fill=(10, 10, 10))
    canvas, _ = letterbox_with_meta(img)
    tensor = preprocess(canvas).unsqueeze(0)

    with torch.no_grad():
        logits = model(tensor)
        sal = torch.sigmoid(logits)

    check("logits shape is [1,1,224,224]", tuple(logits.shape) == (1, 1, IMG_SIZE, IMG_SIZE),
          f"got {tuple(logits.shape)}")
    arr = sal.squeeze().cpu().numpy()
    check("sigmoid output within [0,1]", bool(arr.min() >= 0.0 and arr.max() <= 1.0),
          f"min={arr.min():.4f} max={arr.max():.4f}")
    check("output is not constant", float(arr.std()) > 1e-6, f"std={arr.std():.6f}")


def test_synthetic_peak() -> None:
    print("\n[3/4] Synthetic salience: 1200x800 white canvas, one dark rectangle")
    W, H = 1200, 800
    rect = (820, 250, 940, 330)          # x0, y0, x1, y1
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2

    img = Image.new("RGB", (W, H), (255, 255, 255))
    ImageDraw.Draw(img).rectangle(list(rect), fill=(8, 8, 8))

    load_model(WEIGHTS)
    out = predict_saliency(img)
    sal = gaussian_filter(out.saliency, sigma=3.0)
    py, px = np.unravel_index(int(np.argmax(sal)), sal.shape)

    dist = float(np.hypot(px - cx, py - cy))
    diag = float(np.hypot(W, H))
    ratio = dist / diag
    check(f"peak within {PEAK_TOLERANCE:.0%} of rectangle centre",
          ratio <= PEAK_TOLERANCE,
          f"peak=({px},{py}) target=({cx:.0f},{cy:.0f}) dist={dist:.0f}px "
          f"= {ratio:.1%} of diagonal")


def test_alignment() -> None:
    print("\n[4/4] Letterbox alignment: output dims must equal input dims")
    load_model(WEIGHTS)
    for W, H, label in [(1600, 900, "landscape"), (800, 1400, "portrait"),
                        (1000, 1000, "square")]:
        img = Image.new("RGB", (W, H), (250, 250, 250))
        d = ImageDraw.Draw(img)
        d.rectangle([int(W * 0.1), int(H * 0.1), int(W * 0.3), int(H * 0.2)], fill=(20, 20, 20))
        d.rectangle([int(W * 0.6), int(H * 0.7), int(W * 0.8), int(H * 0.85)], fill=(40, 40, 200))

        out = predict_saliency(img)
        check(f"{label} {W}x{H}: saliency is (H,W)=({H},{W})",
              out.saliency.shape == (H, W), f"got {out.saliency.shape}")
        check(f"{label} {W}x{H}: overlay is (H,W,3)=({H},{W},3)",
              out.overlay_bgr.shape == (H, W, 3), f"got {out.overlay_bgr.shape}")


def main() -> int:
    print("=" * 70)
    print("DesignEye model self-verification")
    print(f"weights: {WEIGHTS}")
    print("=" * 70)

    if not WEIGHTS.is_file():
        print(f"\nFATAL: weights not found at {WEIGHTS}")
        return 2

    test_strict_load()
    test_forward_pass()
    test_synthetic_peak()
    test_alignment()

    print("\n" + "=" * 70)
    print(f"RESULT: {len(_passes)} passed, {len(_failures)} failed")
    if _failures:
        print("FAILED CHECKS:")
        for f in _failures:
            print(f"  - {f}")
        print("\nDo NOT build on this inference path until these pass.")
        return 1
    print("All checks passed. Inference path is sound.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
