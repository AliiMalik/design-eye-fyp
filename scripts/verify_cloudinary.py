"""Verify the Cloudinary backend end to end before trusting it with real data.

Exercises the full round-trip for BOTH resource types Cloudinary distinguishes:
a PNG overlay (resource_type=image) and a .npy saliency array (raw). The raw
path is the one that matters -- reruns and A/B comparison read the .npy back, so
an addressing mistake there fails silently until a user clicks Rerun.

    python scripts/verify_cloudinary.py          # uses backend/.env
    python scripts/verify_cloudinary.py --keep   # do not delete the test objects
"""

from __future__ import annotations

import argparse
import io
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    import numpy as np
    from dotenv import load_dotenv
    from PIL import Image
except ModuleNotFoundError as exc:  # wrong interpreter, almost always
    print(f"Missing dependency: {exc.name}")
    print(f"\nRun this with the project's virtualenv, not the system Python:")
    print(f'  {ROOT / ".venv" / "Scripts" / "python.exe"} scripts\\verify_cloudinary.py')
    raise SystemExit(2) from exc

# Settings resolve env_file relative to the process CWD, so running this from
# the repo root would silently read the root .env instead of the backend's.
# Load the backend file explicitly so the script works from anywhere.
load_dotenv(ROOT / "backend" / ".env", override=False)

from app.config import settings  # noqa: E402

_passes: list[str] = []
_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (_passes if ok else _failures).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true",
                        help="leave the test objects in Cloudinary")
    args = parser.parse_args()

    print("=" * 70)
    print("Cloudinary backend verification")
    print("=" * 70)

    missing = [n for n in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                           "CLOUDINARY_API_SECRET") if not getattr(settings, n)]
    if missing:
        print(f"\nMissing credentials: {', '.join(missing)}")
        print("Set them in backend/.env (and the root .env for Docker), then rerun.")
        return 2

    print(f"cloud_name      : {settings.CLOUDINARY_CLOUD_NAME}")
    print(f"STORAGE_BACKEND : {settings.STORAGE_BACKEND}")
    if settings.STORAGE_BACKEND != "cloudinary":
        print("  note: backend is not 'cloudinary' yet; testing the class directly.")

    try:
        from app.services.storage import CloudinaryStorage
        store = CloudinaryStorage()
    except Exception as exc:  # noqa: BLE001
        print(f"\nFAILED to initialise: {type(exc).__name__}: {exc}")
        print("If this is ModuleNotFoundError, run: pip install cloudinary")
        return 1

    tenant = f"verify-{uuid.uuid4().hex[:8]}"
    png_key = store.tenant_key(tenant, "results", "sample_heatmap.png")
    npy_key = store.tenant_key(tenant, "results", "sample_saliency.npy")

    # --- image round-trip -------------------------------------------------
    print("\n[1/4] PNG (resource_type=image)")
    img = Image.new("RGB", (64, 48), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    original_png = buf.getvalue()

    url = store.save_bytes(png_key, original_png, "image/png")
    check("upload returns a secure URL", url.startswith("https://"), url[:70])
    check("exists() finds it", store.exists(png_key))
    fetched = store.read_bytes(png_key)
    check("read_bytes returns PNG bytes", fetched[:8] == b"\x89PNG\r\n\x1a\n",
          f"{len(fetched)} bytes")
    back = Image.open(io.BytesIO(fetched))
    check("image survives the round-trip", back.size == (64, 48), f"{back.size}")

    # --- raw round-trip ---------------------------------------------------
    print("\n[2/4] .npy (resource_type=raw) - the rerun / A-B path")
    array = np.random.default_rng(7).random((32, 24)).astype(np.float32)
    npy_url = store.save_npy(npy_key, array)
    check("upload returns a secure URL", npy_url.startswith("https://"), npy_url[:70])
    check("exists() finds it", store.exists(npy_key),
          "raw objects need resource_type=raw on the lookup")

    try:
        restored = store.read_npy(npy_key)
        check("array round-trips byte-exact", np.allclose(restored, array),
              f"shape {restored.shape} dtype {restored.dtype}")
    except Exception as exc:  # noqa: BLE001
        check("array round-trips byte-exact", False, f"{type(exc).__name__}: {exc}")

    # --- URL addressing ---------------------------------------------------
    print("\n[3/4] URL addressing")
    png_url = store.url_for(png_key)
    raw_url = store.url_for(npy_key)
    check("image URL carries /image/", "/image/" in png_url, png_url[:80])
    check("raw URL carries /raw/", "/raw/" in raw_url, raw_url[:80])
    check("image URL keeps the extension", png_url.endswith(".png"))
    check("raw URL keeps the .npy", raw_url.endswith(".npy"))
    check("tenant prefix preserved in the URL", tenant in png_url and tenant in raw_url)

    # --- cleanup ----------------------------------------------------------
    print("\n[4/4] delete")
    if args.keep:
        print("  (skipped: --keep)")
    else:
        store.delete(png_key)
        store.delete(npy_key)
        check("image removed", not store.exists(png_key))
        check("raw removed", not store.exists(npy_key))

    print("\n" + "=" * 70)
    print(f"RESULT: {len(_passes)} passed, {len(_failures)} failed")
    if _failures:
        for f in _failures:
            print(f"  - {f}")
        print("\nDo NOT switch STORAGE_BACKEND=cloudinary until these pass.")
        return 1
    print("Cloudinary backend is sound. Safe to set STORAGE_BACKEND=cloudinary.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
