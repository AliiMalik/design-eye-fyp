"""Package extension/ into the ZIP the website hands out.

Chrome will not install an extension from anywhere but the Web Store, so the
site cannot install it for the user. What it can do is give them a clean folder
and get out of the way -- which means the archive has to unzip to exactly what
"Load unpacked" expects, with no wrapper directory and nothing extraneous.

Run after changing anything under extension/:

    python scripts/build_extension.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "extension"
OUT = ROOT / "frontend" / "public" / "designeye-extension.zip"

# Development-only files. Shipping tests would work but invites questions about
# code the user cannot run, and Chrome Web Store review flags unused files.
EXCLUDE_DIRS = {"test", "node_modules", "__pycache__"}
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}


def collect() -> list[Path]:
    files: list[Path] = []
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SRC)
        if set(rel.parts) & EXCLUDE_DIRS or rel.name in EXCLUDE_NAMES:
            continue
        files.append(path)
    return files


def main() -> int:
    manifest_path = SRC / "manifest.json"
    if not manifest_path.is_file():
        print("No manifest.json — is extension/ present?", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = collect()

    names = {f.relative_to(SRC).as_posix() for f in files}
    required = {"manifest.json", "popup.html", "popup.js", "popup.css", "background.js"}
    missing = required - names
    if missing:
        print(f"Refusing to build: missing {sorted(missing)}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic: a fixed timestamp keeps the archive byte-identical when
    # nothing changed, so it does not churn in git on every build.
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(SRC).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()[:12]
    size_kb = OUT.stat().st_size / 1024
    print(f"{OUT.relative_to(ROOT)}  {size_kb:.1f} KB  sha256:{digest}")
    print(f"  version {manifest['version']}, {len(files)} files")
    for f in files:
        print(f"    {f.relative_to(SRC).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
