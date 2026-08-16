"""Score the calibration samples and report the Clarity Score bands.

Targets from the SDS test cases: clean designs > 75 (TC-07), cluttered < 40
(TC-08).

    python scripts/calibrate_clarity.py            # scored table
    python scripts/calibrate_clarity.py --tune     # search the constants
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.ml.inference import load_model, predict_saliency  # noqa: E402
from app.services import analytics  # noqa: E402

WEIGHTS = ROOT / "backend" / "app" / "ml" / "weights" / "stage3_ui_best_val.pth"
SAMPLES = ROOT / "inputs" / "samples"
CLEAN_TARGET = 75.0
CLUTTERED_TARGET = 40.0


def collect() -> list[tuple[str, str, Path]]:
    items: list[tuple[str, str, Path]] = []
    for label in ("clean", "cluttered"):
        folder = SAMPLES / label
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                items.append((label, path.name, path))
    return items


def measure(items: list[tuple[str, str, Path]]) -> list[dict]:
    """Run inference once per sample and cache the raw components."""
    load_model(WEIGHTS)
    rows: list[dict] = []
    for label, name, path in items:
        img = Image.open(path).convert("RGB")
        out = predict_saliency(img)
        rgb = np.array(img, dtype=np.uint8)
        rows.append({
            "label": label,
            "name": name,
            "focus_raw": analytics.compute_focus_index(out.saliency),
            "edge_density": analytics.compute_edge_density(rgb),
        })
    return rows


def score_row(row: dict) -> tuple[float, float, float]:
    focus = analytics.normalise_focus(row["focus_raw"])
    clutter = float(np.clip(row["edge_density"] / analytics.EDGE_DENSITY_SCALE, 0.0, 1.0))
    return analytics.compute_clarity_score(focus, clutter), focus, clutter


def print_table(rows: list[dict]) -> tuple[bool, bool]:
    print(f"\n{'label':<10} {'sample':<28} {'focus_raw':>9} {'focus_n':>8} "
          f"{'edge_den':>9} {'clutter':>8} {'clarity':>8}")
    print("-" * 84)

    clean_scores, cluttered_scores = [], []
    for row in rows:
        clarity, focus_n, clutter = score_row(row)
        (clean_scores if row["label"] == "clean" else cluttered_scores).append(clarity)
        print(f"{row['label']:<10} {row['name'][:28]:<28} {row['focus_raw']:>9.4f} "
              f"{focus_n:>8.4f} {row['edge_density']:>9.4f} {clutter:>8.4f} "
              f"{clarity:>8.2f}")

    print("-" * 84)
    clean_ok = bool(clean_scores) and min(clean_scores) > CLEAN_TARGET
    clut_ok = bool(cluttered_scores) and max(cluttered_scores) < CLUTTERED_TARGET

    if clean_scores:
        print(f"clean      n={len(clean_scores):<2} min={min(clean_scores):6.2f} "
              f"mean={np.mean(clean_scores):6.2f} max={max(clean_scores):6.2f}  "
              f"target > {CLEAN_TARGET}  [{'PASS' if clean_ok else 'FAIL'}]")
    if cluttered_scores:
        print(f"cluttered  n={len(cluttered_scores):<2} min={min(cluttered_scores):6.2f} "
              f"mean={np.mean(cluttered_scores):6.2f} max={max(cluttered_scores):6.2f}  "
              f"target < {CLUTTERED_TARGET}  [{'PASS' if clut_ok else 'FAIL'}]")

    if clean_scores and cluttered_scores:
        print(f"\nseparation: {min(clean_scores) - max(cluttered_scores):+.2f} points "
              f"between the worst clean and the best cluttered sample")
    return clean_ok, clut_ok


def tune(rows: list[dict]) -> None:
    """Grid-search the constants for the widest margin against both targets."""
    clean = [r for r in rows if r["label"] == "clean"]
    clut = [r for r in rows if r["label"] == "cluttered"]
    if not clean or not clut:
        print("Need both clean and cluttered samples to tune.")
        return

    best = None
    for f_min in np.arange(0.02, 0.13, 0.005):
        for f_max in np.arange(0.16, 0.46, 0.01):
            if f_max - f_min < 0.05:
                continue
            for edge_scale in np.arange(0.04, 0.22, 0.005):
                for fw in (0.55, 0.6, 0.65, 0.7, 0.75):
                    cw = 1.0 - fw

                    def sc(r: dict) -> float:
                        fo = float(np.clip((r["focus_raw"] - f_min) / (f_max - f_min), 0, 1))
                        cl = float(np.clip(r["edge_density"] / edge_scale, 0, 1))
                        return 100.0 * (fw * fo + cw * (1.0 - cl))

                    clean_min = min(sc(r) for r in clean)
                    clut_max = max(sc(r) for r in clut)
                    if clean_min <= CLEAN_TARGET or clut_max >= CLUTTERED_TARGET:
                        continue
                    margin = min(clean_min - CLEAN_TARGET, CLUTTERED_TARGET - clut_max)
                    if best is None or margin > best[0]:
                        best = (margin, f_min, f_max, edge_scale, fw,
                                clean_min, clut_max)

    if best is None:
        print("\nNo constant set satisfied both bands. Widen the search or "
              "revisit the sample set.")
        return

    margin, f_min, f_max, edge_scale, fw, clean_min, clut_max = best
    print("\nBest constants found:")
    print(f"  FOCUS_RAW_MIN     = {f_min:.3f}")
    print(f"  FOCUS_RAW_MAX     = {f_max:.3f}")
    print(f"  EDGE_DENSITY_SCALE= {edge_scale:.3f}")
    print(f"  FOCUS_WEIGHT      = {fw:.2f}")
    print(f"  CLUTTER_WEIGHT    = {1 - fw:.2f}")
    print(f"  -> worst clean {clean_min:.2f} (> {CLEAN_TARGET}), "
          f"best cluttered {clut_max:.2f} (< {CLUTTERED_TARGET}), margin {margin:.2f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true",
                        help="grid-search constants instead of just reporting")
    args = parser.parse_args()

    items = collect()
    if not items:
        print("No samples found under inputs/samples/{clean,cluttered}/.")
        print("Run: python scripts/make_samples.py")
        return 0

    print(f"Scoring {len(items)} samples (this runs the model once per image)...")
    rows = measure(items)

    print("\nCurrent constants: "
          f"FOCUS_WEIGHT={analytics.FOCUS_WEIGHT} "
          f"CLUTTER_WEIGHT={analytics.CLUTTER_WEIGHT} "
          f"EDGE_THRESHOLD={analytics.EDGE_THRESHOLD} "
          f"EDGE_DENSITY_SCALE={analytics.EDGE_DENSITY_SCALE} "
          f"FOCUS_RAW_MIN={analytics.FOCUS_RAW_MIN} "
          f"FOCUS_RAW_MAX={analytics.FOCUS_RAW_MAX}")

    clean_ok, clut_ok = print_table(rows)
    if args.tune:
        tune(rows)
    return 0 if (clean_ok and clut_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
