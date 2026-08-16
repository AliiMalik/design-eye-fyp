"""Upload validation and rasterisation (BUILD.md section 4).

Accepts PNG / JPG / JPEG / WEBP directly, rasterises SVG at 2x and page 1 of a
PDF at 150 DPI. The SDS restricts uploads to SVG/PDF; that is overridden here
because the model consumes raster images -- see docs/DEVIATIONS.md.

Content type is sniffed from the actual bytes. The client-supplied filename and
content-type header are never trusted.
"""

from __future__ import annotations

import io
import logging

from PIL import Image

from app.config import settings
from app.models.domain import AssetFormat

logger = logging.getLogger(__name__)

SVG_RASTER_SCALE = 2.0
PDF_RASTER_DPI = 150
Image.MAX_IMAGE_PIXELS = 200_000_000  # guard against decompression bombs


class UnsupportedFileError(ValueError):
    """Raised for any upload we cannot or will not process."""


SUPPORTED_LABEL = "PNG, JPG, JPEG, WEBP, SVG, or PDF"


def sniff_format(data: bytes) -> AssetFormat:
    """Identify the real format from magic bytes. Never trusts the extension."""
    if len(data) < 12:
        raise UnsupportedFileError(f"File is empty or truncated. Supported: {SUPPORTED_LABEL}.")

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return AssetFormat.PNG
    if data.startswith(b"\xff\xd8\xff"):
        return AssetFormat.JPEG
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return AssetFormat.WEBP
    if data.startswith(b"%PDF"):
        return AssetFormat.PDF

    head = data[:1024].lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in data[:4096].lower():
        return AssetFormat.SVG

    raise UnsupportedFileError(
        f"Invalid file format. Supported formats are {SUPPORTED_LABEL}."
    )


def validate_size(data: bytes) -> None:
    """Enforce the upload size ceiling."""
    if not data:
        raise UnsupportedFileError("Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise UnsupportedFileError(
            f"File size exceeds {settings.MAX_UPLOAD_MB}MB limit."
        )


def _rasterise_svg(data: bytes) -> Image.Image:
    try:
        import cairosvg
    except (ImportError, OSError) as exc:  # cairo native libs may be absent
        raise UnsupportedFileError(
            "SVG rasterisation is unavailable on this server. "
            "Export the mockup as PNG and upload that instead."
        ) from exc
    png_bytes = cairosvg.svg2png(bytestring=data, scale=SVG_RASTER_SCALE)
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def _rasterise_pdf(data: bytes) -> Image.Image:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise UnsupportedFileError(
            "PDF rasterisation is unavailable on this server. "
            "Export the mockup as PNG and upload that instead."
        ) from exc

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise UnsupportedFileError("PDF contains no pages.")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=PDF_RASTER_DPI)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    finally:
        doc.close()


def load_image(data: bytes, fmt: AssetFormat | None = None) -> tuple[Image.Image, AssetFormat]:
    """Validate and decode an upload into a PIL image.

    Returns ``(image, detected_format)``. Raises UnsupportedFileError with a
    client-safe message on anything we cannot process.
    """
    validate_size(data)
    fmt = fmt or sniff_format(data)

    try:
        if fmt == AssetFormat.SVG:
            img = _rasterise_svg(data)
        elif fmt == AssetFormat.PDF:
            img = _rasterise_pdf(data)
        else:
            img = Image.open(io.BytesIO(data))
            img.load()
            img = img.convert("RGB")
    except UnsupportedFileError:
        raise
    except Exception as exc:  # noqa: BLE001 - decoder errors become 400s
        logger.warning("Failed to decode upload (format=%s): %s", fmt, exc)
        raise UnsupportedFileError(
            f"The file could not be read as an image. Supported: {SUPPORTED_LABEL}."
        ) from exc

    long_side = max(img.size)
    if long_side > settings.MAX_IMAGE_LONG_SIDE:
        raise UnsupportedFileError(
            f"Image is too large ({img.width}x{img.height}). "
            f"The longest side must be at most {settings.MAX_IMAGE_LONG_SIDE}px."
        )
    if img.width < 16 or img.height < 16:
        raise UnsupportedFileError("Image is too small to analyse (minimum 16x16).")

    return img, fmt


def encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
