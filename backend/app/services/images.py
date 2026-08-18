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
# A Figma "export frames to PDF" can carry dozens of screens. Cap the fan-out so
# one upload cannot pin a worker for minutes.
MAX_PDF_PAGES = 30
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


def size_limit_mb(fmt: AssetFormat | None = None) -> int:
    """The ceiling that applies to this format.

    A PDF gets more headroom than an image: a genuine multi-screen export is
    routinely larger than any single mockup, and the PDF is never stored -- only
    the pages rasterised out of it are.
    """
    if fmt == AssetFormat.PDF:
        return max(settings.MAX_PDF_UPLOAD_MB, settings.MAX_UPLOAD_MB)
    return settings.MAX_UPLOAD_MB


def validate_size(data: bytes, fmt: AssetFormat | None = None) -> None:
    """Enforce the upload size ceiling for this format."""
    if not data:
        raise UnsupportedFileError("Uploaded file is empty.")
    limit_mb = size_limit_mb(fmt)
    if len(data) > limit_mb * 1024 * 1024:
        raise UnsupportedFileError(f"File size exceeds {limit_mb}MB limit.")


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


def count_pdf_pages(data: bytes) -> int:
    """Page count, or 0 when the bytes are not a readable PDF."""
    try:
        import fitz
    except ImportError:
        return 0
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001 - a malformed PDF is simply not countable
        return 0
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def load_pdf_pages(data: bytes, limit: int = MAX_PDF_PAGES) -> list[Image.Image]:
    """Rasterise every page of a multi-screen PDF, in document order.

    ``load_image`` deliberately returns only page 1 to keep the single-upload
    contract; this is the fan-out path used by batch upload.
    """
    validate_size(data, AssetFormat.PDF)
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise UnsupportedFileError(
            "PDF rasterisation is unavailable on this server. "
            "Export the screens as PNG and upload them individually."
        ) from exc

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise UnsupportedFileError("PDF contains no pages.")

        pages: list[Image.Image] = []
        for index in range(min(doc.page_count, limit)):
            pix = doc.load_page(index).get_pixmap(dpi=PDF_RASTER_DPI)
            page = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

            long_side = max(page.size)
            if long_side > settings.MAX_IMAGE_LONG_SIDE:
                scale = settings.MAX_IMAGE_LONG_SIDE / float(long_side)
                page = page.resize(
                    (max(1, int(page.width * scale)), max(1, int(page.height * scale))),
                    Image.LANCZOS,
                )
            if page.width < 16 or page.height < 16:
                continue  # blank or degenerate page, nothing to analyse
            pages.append(page)

        if not pages:
            raise UnsupportedFileError("No analysable pages found in this PDF.")
        return pages
    finally:
        doc.close()


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
    # Sniff before measuring: the ceiling depends on the real format, and the
    # filename is never trusted to tell us what that is.
    if not data:
        raise UnsupportedFileError("Uploaded file is empty.")
    fmt = fmt or sniff_format(data)
    validate_size(data, fmt)

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

    # Width and length are bounded separately. A scrolling page is legitimately
    # very long, so only its narrow axis is held to the ordinary limit.
    if min(img.size) > settings.MAX_IMAGE_LONG_SIDE:
        raise UnsupportedFileError(
            f"This design is {img.width}x{img.height}, which is too big to "
            f"analyse. Its shorter side needs to be under "
            f"{settings.MAX_IMAGE_LONG_SIDE}px."
        )
    if max(img.size) > settings.MAX_SCROLL_LONG_SIDE:
        raise UnsupportedFileError(
            f"This design is {img.width}x{img.height}, which is longer than we "
            f"can analyse. Split it up, or keep the longer side under "
            f"{settings.MAX_SCROLL_LONG_SIDE}px."
        )
    if img.width < 16 or img.height < 16:
        raise UnsupportedFileError("Image is too small to analyse (minimum 16x16).")

    return img, fmt


def encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
