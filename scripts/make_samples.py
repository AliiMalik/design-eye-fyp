"""Build the clarity-calibration sample set.

No clean/cluttered corpus was supplied with the inputs, so this script assembles
a reproducible one: the genuinely minimal Visily screens serve as real "clean"
examples, and synthetic mockups span both ends of the density spectrum. Anyone
can regenerate the exact set, which is what makes the calibration defensible.

    python scripts/make_samples.py
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "inputs" / "screens"
CLEAN = ROOT / "inputs" / "samples" / "clean"
CLUTTERED = ROOT / "inputs" / "samples" / "cluttered"

W, H = 1440, 900
INK = (17, 24, 39)
MUTED = (148, 163, 184)
ACCENT = (79, 91, 213)
BG = (255, 255, 255)

# Real Visily screens that are genuinely minimal, centred-card layouts.
REAL_CLEAN = [
    ("visily-designeye-login.jpg", "real_login.png"),
    ("visily-container.jpg", "real_password_reset.png"),
    ("visily-designeye-user-registration.jpg", "real_registration.png"),
    ("visily-export-analysis-report-generation.jpg", "real_export_modal.png"),
]


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def clean_hero(path: Path) -> None:
    """One headline, one CTA, enormous whitespace."""
    img, d = _canvas()
    d.rectangle([0, 0, W, 64], fill=BG)
    d.rectangle([80, 28, 190, 40], fill=INK)
    d.rectangle([420, 250, 1020, 300], fill=INK)
    d.rectangle([500, 320, 940, 352], fill=MUTED)
    d.rectangle([620, 420, 820, 472], fill=ACCENT)
    img.save(path)


def clean_centered_card(path: Path) -> None:
    """Single centred form card on a plain field."""
    img, d = _canvas()
    d.rounded_rectangle([520, 220, 920, 680], radius=18, fill=(250, 250, 252),
                        outline=(226, 232, 240), width=2)
    d.rectangle([690, 270, 750, 330], fill=ACCENT)
    d.rectangle([620, 360, 820, 386], fill=INK)
    for y in (430, 510):
        d.rounded_rectangle([570, y, 870, y + 44], radius=8, fill=BG,
                            outline=(226, 232, 240), width=2)
    d.rounded_rectangle([570, 590, 870, 638], radius=8, fill=ACCENT)
    img.save(path)


def clean_split_feature(path: Path) -> None:
    """Two-column split: text left, single image block right."""
    img, d = _canvas()
    d.rectangle([100, 300, 620, 348], fill=INK)
    d.rectangle([100, 372, 560, 396], fill=MUTED)
    d.rectangle([100, 410, 500, 434], fill=MUTED)
    d.rounded_rectangle([100, 490, 300, 540], radius=25, fill=ACCENT)
    d.rounded_rectangle([760, 220, 1340, 680], radius=20, fill=(238, 242, 255))
    img.save(path)


def cluttered_dense_dashboard(path: Path, seed: int = 1) -> None:
    """Many small cards, each packed with text lines."""
    rng = random.Random(seed)
    img, d = _canvas()
    d.rectangle([0, 0, W, 56], fill=(30, 41, 89))
    for i in range(9):
        d.rectangle([20 + i * 150, 18, 20 + i * 150 + 120, 38], fill=(200, 205, 230))

    for row in range(4):
        for col in range(6):
            x, y = 20 + col * 236, 80 + row * 205
            d.rectangle([x, y, x + 220, y + 190], fill=(252, 252, 253),
                        outline=(203, 213, 225), width=2)
            for line in range(7):
                lw = rng.randint(70, 200)
                d.rectangle([x + 10, y + 16 + line * 24, x + 10 + lw,
                             y + 28 + line * 24], fill=(120, 130, 150))
    img.save(path)


def cluttered_data_table(path: Path, seed: int = 2) -> None:
    """A dense grid: every cell bordered, every cell full."""
    rng = random.Random(seed)
    img, d = _canvas()
    cols, rows = 9, 26
    cw, rh = W // cols, (H - 40) // rows
    for r in range(rows):
        for c in range(cols):
            x, y = c * cw, 40 + r * rh
            d.rectangle([x, y, x + cw, y + rh], outline=(148, 163, 184), width=1)
            d.rectangle([x + 6, y + 6, x + rng.randint(30, cw - 10), y + rh - 8],
                        fill=(90, 100, 120))
    img.save(path)


def cluttered_text_wall(path: Path, seed: int = 3) -> None:
    """Edge-to-edge body copy with no hierarchy."""
    rng = random.Random(seed)
    img, d = _canvas()
    y = 24
    while y < H - 20:
        x = 24
        while x < W - 40:
            wdt = rng.randint(30, 120)
            d.rectangle([x, y, min(x + wdt, W - 24), y + 12], fill=(60, 70, 90))
            x += wdt + rng.randint(8, 16)
        y += 22
    img.save(path)


def cluttered_noisy_grid(path: Path, seed: int = 4) -> None:
    """Overlapping blocks of competing colour and weight."""
    rng = random.Random(seed)
    img, d = _canvas()
    palette = [(239, 68, 68), (34, 197, 94), (59, 130, 246), (234, 179, 8),
               (168, 85, 247), (14, 165, 233)]
    for _ in range(260):
        x, y = rng.randint(0, W - 60), rng.randint(0, H - 60)
        w, h = rng.randint(24, 150), rng.randint(18, 90)
        d.rectangle([x, y, x + w, y + h], fill=rng.choice(palette),
                    outline=(15, 23, 42), width=2)
    img.save(path)


def cluttered_ad_heavy(path: Path, seed: int = 5) -> None:
    """Content squeezed between banners, rails, and boxed promos."""
    rng = random.Random(seed)
    img, d = _canvas()
    d.rectangle([0, 0, W, 110], fill=(254, 226, 226), outline=(220, 38, 38), width=3)
    for i in range(6):
        d.rectangle([20 + i * 235, 20, 20 + i * 235 + 200, 90],
                    fill=(254, 202, 202), outline=(185, 28, 28), width=2)
    for side_x in (0, W - 240):
        for i in range(5):
            y = 130 + i * 150
            d.rectangle([side_x + 10, y, side_x + 230, y + 135],
                        fill=(224, 231, 255), outline=(67, 56, 202), width=2)
            for line in range(4):
                d.rectangle([side_x + 22, y + 14 + line * 28,
                             side_x + 22 + rng.randint(60, 190), y + 28 + line * 28],
                            fill=(99, 102, 241))
    for i in range(14):
        y = 130 + i * 52
        d.rectangle([260, y, 260 + rng.randint(300, 900), y + 30], fill=(71, 85, 105))
    img.save(path)


def main() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    CLUTTERED.mkdir(parents=True, exist_ok=True)
    for folder in (CLEAN, CLUTTERED):
        for old in folder.glob("*.png"):
            old.unlink()

    copied = 0
    for src_name, dst_name in REAL_CLEAN:
        src = SCREENS / src_name
        if src.is_file():
            Image.open(src).convert("RGB").save(CLEAN / dst_name)
            copied += 1

    clean_hero(CLEAN / "synth_hero.png")
    clean_centered_card(CLEAN / "synth_centered_card.png")
    clean_split_feature(CLEAN / "synth_split_feature.png")

    cluttered_dense_dashboard(CLUTTERED / "synth_dense_dashboard.png")
    cluttered_data_table(CLUTTERED / "synth_data_table.png")
    cluttered_text_wall(CLUTTERED / "synth_text_wall.png")
    cluttered_noisy_grid(CLUTTERED / "synth_noisy_grid.png")
    cluttered_ad_heavy(CLUTTERED / "synth_ad_heavy.png")

    print(f"clean/     {len(list(CLEAN.glob('*.png')))} images "
          f"({copied} real Visily screens + 3 synthetic)")
    print(f"cluttered/ {len(list(CLUTTERED.glob('*.png')))} images (5 synthetic)")


if __name__ == "__main__":
    main()
