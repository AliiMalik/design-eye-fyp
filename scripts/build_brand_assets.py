"""Generate every derived brand asset from the one source logo.

The mark appears in more places than is obvious -- marketing nav, app sidebar,
auth screens, browser tab, extension toolbar, extension popup -- on four
different backgrounds and at sizes from 16px to 512px. Doing that by hand
guarantees one of them stays on the old artwork for months.

    python scripts/build_brand_assets.py

Three things the source artwork forces on us.

**It is recoloured.** The supplied rings run through #FE0500 and #FE9200, within
a few points of --color-danger and --color-warning. A mark built from the two
colours the product uses to say "something is wrong" reads as an error state in
the nav. The geometry is kept exactly; only the palette moves onto the brand
ramp, and the order is reversed so the bright ring sits at the pupil -- the
attention peak, which is the thing the product measures -- while a solid indigo
rim carries the silhouette.

**Rings are dropped as it shrinks.** Five concentric strokes need roughly 3px
each to stay separate, so below ~48px they collapse into a smudge. Five rings
large, three medium.

**Below ~24px it stops being line work.** The gap between the pupil and the
first ring is under a pixel there, so no stroke weight saves it. The tiny tier
is a filled lens instead: same silhouette, same bright-centre reading, but mass
rather than contour.

The tiers never appear side by side.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "inputs" / "brand" / "logo-source.png"

ASSETS = ROOT / "frontend" / "assets" / "brand"
NEXT_APP = ROOT / "frontend" / "app"
EXT_ICONS = ROOT / "extension" / "icons"

# The six flat colours in the supplied artwork, innermost first. Measured rather
# than guessed -- the export is slightly noisy, so pixels match to the nearest.
SRC_RINGS = np.array(
    [(0, 8, 65), (0, 32, 201), (0, 27, 255), (148, 0, 216), (254, 5, 0), (254, 146, 0)],
    dtype=float,
)


def ramp(*hexes: str) -> np.ndarray:
    return np.array([[int(h[i : i + 2], 16) for i in (1, 3, 5)] for h in hexes], float)


def rgb(hexcol: str) -> tuple[int, int, int]:
    r, g, b = (int(hexcol[i : i + 2], 16) for i in (1, 3, 5))
    return r, g, b


# Innermost -> outermost.
LIGHT = ramp("#1B2559", "#22D3EE", "#818CF8", "#A78BFA", "#7C3AED", "#4149B4")

# Used on #0A0A0F, #14141C *and* the always-navy #1B2559 sidebar, so the pupil
# is darker than navy-900 instead of merging into it, and the rim lifts to
# indigo-600 to stay visible on all three.
DARK = ramp("#0A0E28", "#22D3EE", "#A5B0FB", "#A78BFA", "#8B5CF6", "#4F5BD5")

# The favicon and the toolbar icon are one artwork for both light and dark
# browser chrome. Solid indigo carries on white and on Chrome's #202124 alike,
# and the cyan pupil keeps its own contrast against the body on either.
TINY_BODY, TINY_PUPIL = "#4F5BD5", "#22D3EE"

FULL, COMPACT = (0, 1, 2, 3, 4, 5), (0, 1, 2)


def classify(src: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Label each pixel with its ring. Alpha carries the antialiasing in this
    artwork, so edge pixels keep their ring's colour and land in the right class."""
    a = np.asarray(src.convert("RGBA")).astype(float)
    idx = ((a[..., :3][:, :, None, :] - SRC_RINGS[None, None, :, :]) ** 2).sum(-1).argmin(-1)
    return idx, a[..., 3]


def _layer(shape: tuple[int, int], colour: str, mask: np.ndarray) -> Image.Image:
    flat = np.empty((*shape, 3), np.uint8)
    flat[:] = rgb(colour)
    return Image.fromarray(np.dstack([flat, mask.astype(np.uint8)]), "RGBA")


def render(idx: np.ndarray, alpha: np.ndarray, palette: np.ndarray,
           keep: tuple[int, ...]) -> Image.Image:
    """Composite the kept rings, outermost first.

    One layer per ring rather than one recoloured bitmap: the transparent gaps
    classify as whichever ring they are nearest, so a single combined mask would
    flood those gaps with the wrong colour.
    """
    canvas = Image.new("RGBA", idx.shape[::-1], (0, 0, 0, 0))
    for ring in sorted(keep, reverse=True):
        colour = "#{:02X}{:02X}{:02X}".format(*palette[ring].astype(int))
        canvas.alpha_composite(_layer(idx.shape, colour, np.where(idx == ring, alpha, 0)))
    return canvas.crop(canvas.getbbox())


def solid(idx: np.ndarray, alpha: np.ndarray) -> Image.Image:
    """Flood ring 2's outline and stamp the pupil back on top.

    Ring 2 rather than ring 1 for the body: filling the innermost ring leaves
    the pupil taking up most of the lens, which reads as a cyan blob with a rim
    instead of an eye. Ring 3 is the other way -- the pupil shrinks to a speck.
    """
    ring = (np.where(idx == 2, alpha, 0) > 40).astype(np.uint8) * 255
    # .copy() is load-bearing: fromarray wraps the numpy buffer read-only, and
    # floodfill's writes are then discarded in silence, leaving every pixel
    # "inside" and the icon a solid rectangle.
    probe = Image.fromarray(ring, "L").copy()
    ImageDraw.floodfill(probe, (0, 0), 128)      # reaches only outside the closed loop
    body = np.asarray(probe) == 0                # strictly enclosed, so stray
    filled = float(body.mean())                  # antialiased specks stay out
    if not 0.02 < filled < 0.6:
        raise RuntimeError(
            f"flood produced an implausible body ({filled:.3f} of canvas): the ring "
            "is not a closed loop, or the writes were dropped again"
        )

    canvas = Image.new("RGBA", idx.shape[::-1], (0, 0, 0, 0))
    canvas.alpha_composite(_layer(idx.shape, TINY_BODY, body * 255))
    pupil = (np.where(idx == 0, alpha, 0) > 40) * 255
    canvas.alpha_composite(_layer(idx.shape, TINY_PUPIL, pupil))
    return canvas.crop(canvas.getbbox())


def wide(mark: Image.Image, width: int) -> Image.Image:
    return mark.resize((width, max(1, round(width * mark.height / mark.width))), Image.LANCZOS)


def square(mark: Image.Image, size: int, inset: float = 0.96,
           bg: str | None = None) -> Image.Image:
    """Fit the wide mark into the square frame an OS icon is drawn in."""
    scaled = wide(mark, max(1, round(size * inset)))
    frame = Image.new("RGBA", (size, size), (*rgb(bg), 255) if bg else (0, 0, 0, 0))
    frame.alpha_composite(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2))
    return frame


def save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    print(f"  {path.relative_to(ROOT).as_posix():<44} {img.width}x{img.height}")


def main() -> int:
    if not SOURCE.is_file():
        print(f"Missing {SOURCE.relative_to(ROOT)}", file=sys.stderr)
        return 1

    idx, alpha = classify(Image.open(SOURCE))
    full = {t: render(idx, alpha, p, FULL) for t, p in (("light", LIGHT), ("dark", DARK))}
    compact = {t: render(idx, alpha, p, COMPACT) for t, p in (("light", LIGHT), ("dark", DARK))}
    tiny = solid(idx, alpha)

    print("web app  (imported by components/brand.tsx)")
    # Roughly 7x the largest place each is drawn -- headroom for retina and for
    # next/image to resize down from, without a 200KB logo in the bundle.
    for theme in ("light", "dark"):
        save(wide(full[theme], 540), ASSETS / f"mark-{theme}.png")
        save(wide(compact[theme], 300), ASSETS / f"mark-compact-{theme}.png")

    # Browsers pick either of these for the tab and scale it to 16px, so both
    # are the tiny tier. iOS composites transparency to black, so the home
    # screen icon gets an opaque canvas and the richer compact mark.
    print("browser tab")
    save(square(tiny, 512, inset=0.92), NEXT_APP / "icon.png")
    save(square(compact["light"], 180, inset=0.78, bg="#FFFFFF"), NEXT_APP / "apple-icon.png")
    ico = NEXT_APP / "favicon.ico"
    square(tiny, 64, inset=0.92).save(
        ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
    )
    print(f"  {ico.relative_to(ROOT).as_posix():<44} 16,32,48,64")

    # 16 rides Chrome's toolbar, which follows the OS theme, so it takes the
    # dual-safe tiny mark. 48 and 128 are only drawn on chrome://extensions.
    print("extension")
    save(square(tiny, 16, inset=1.0), EXT_ICONS / "16.png")
    save(square(compact["light"], 48), EXT_ICONS / "48.png")
    save(square(full["light"], 128), EXT_ICONS / "128.png")
    for theme in ("light", "dark"):
        save(wide(compact[theme], 160), EXT_ICONS / f"mark-{theme}.png")

    # A stale archive hands every new user the old icon.
    print("extension archive")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_extension.py")],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return 1
    print("  " + (r.stdout.strip().splitlines() or ["rebuilt"])[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
