"""Normalise an uploaded picture into one stored avatar.

Every surface shows the avatar in a square, so the crop happens once here
rather than each consumer picking its own.

Deliberately not routed through ``images.load_image``: that path is tuned for
mockups. It accepts PDF and SVG, allows a 30000px scrolling page, and its
errors talk about "your design" -- none of which fits a profile picture.
"""

from __future__ import annotations

import hashlib
import io
import logging

from PIL import Image, ImageOps

from app.models.domain import AssetFormat
from app.services.images import UnsupportedFileError, sniff_format
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

AVATAR_PX = 256
AVATAR_MAX_MB = 5
AVATAR_MAX_SIDE = 8000
# Raster only. A PDF or an SVG is a legitimate mockup but not a face, and
# rasterising one here would quietly accept a document page as someone's photo.
ALLOWED = (AssetFormat.PNG, AssetFormat.JPEG, AssetFormat.WEBP)


def build_avatar(raw: bytes) -> bytes:
    """Validate, straighten, square-crop and shrink an upload to a single PNG."""
    if not raw:
        raise UnsupportedFileError("The file is empty.")
    if len(raw) > AVATAR_MAX_MB * 1024 * 1024:
        raise UnsupportedFileError(f"Profile pictures must be under {AVATAR_MAX_MB}MB.")
    if sniff_format(raw) not in ALLOWED:
        raise UnsupportedFileError("Profile pictures must be a PNG, JPG, or WEBP image.")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:  # noqa: BLE001 - decoder errors become 400s
        logger.warning("Failed to decode an avatar upload: %s", exc)
        raise UnsupportedFileError("That image could not be read.") from exc

    if max(img.size) > AVATAR_MAX_SIDE:
        raise UnsupportedFileError(
            f"That image is {img.width}x{img.height}, which is larger than we "
            f"can handle. Keep the longest side under {AVATAR_MAX_SIDE}px."
        )

    # Phone cameras record the rotation in EXIF rather than in the pixels, so
    # without this a portrait photo arrives lying on its side.
    img = ImageOps.exif_transpose(img) or img

    if img.mode in ("RGBA", "LA", "P"):
        # A plain convert("RGB") composites transparency onto black, which
        # gives a cut-out PNG a black box instead of the card behind it.
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
        img = flat
    else:
        img = img.convert("RGB")

    square = ImageOps.fit(img, (AVATAR_PX, AVATAR_PX), Image.LANCZOS, centering=(0.5, 0.5))
    buf = io.BytesIO()
    square.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def avatar_key(user_id: str, data: bytes) -> str:
    """Content-addressed, so a new picture is always a new URL.

    next/image and Cloudinary both cache hard by URL; writing every upload to
    one stable path would keep serving the previous face.
    """
    digest = hashlib.sha1(data).hexdigest()[:12]  # noqa: S324 - a cache key, not a secret
    return StorageService.tenant_key(user_id, "avatar", f"{digest}.png")
