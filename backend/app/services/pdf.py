"""PDF report generation (ReportLab).

Produces the single-result report and the A/B comparison report served by
GET /results/{asset_id}/report.pdf and /compare/{comparison_id}/report.pdf.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

BRAND_NAVY = colors.HexColor("#1B2559")
BRAND_INDIGO = colors.HexColor("#4F5BD5")
BRAND_MUTED = colors.HexColor("#64748B")
BRAND_LINE = colors.HexColor("#E2E8F0")

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 36 * mm


# Mirrors BASIS_LABEL in components/app/suggestions-panel.tsx. The raw field
# name is machine-read; printing it in a report shown to a client is a leak.
BASIS_LABEL = {
    "clarity_score": "Clarity Score",
    "focus_order": "Focus order",
    "region_saliency": "Region saliency",
    "clutter_index": "Clutter index",
}


def _basis(item: dict) -> str:
    raw = str(item.get("based_on", ""))
    return BASIS_LABEL.get(raw, raw.replace("_", " ").capitalize())


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=22, textColor=BRAND_NAVY, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9.5,
                              textColor=BRAND_MUTED, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=13, textColor=BRAND_NAVY,
                             spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=14,
                               alignment=TA_LEFT, textColor=colors.HexColor("#1E293B")),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8,
                                textColor=BRAND_MUTED),
    }


def _fit_image(data: bytes, max_w: float, max_h: float) -> RLImage | None:
    """Scale an image to fit a box while preserving aspect ratio."""
    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(data)) as probe:
            w, h = probe.size
        scale = min(max_w / w, max_h / h)
        return RLImage(io.BytesIO(data), width=w * scale, height=h * scale)
    except Exception as exc:  # noqa: BLE001 - a bad image must not kill the report
        logger.warning("Could not embed image in PDF: %s", exc)
        return None


def _downscale_png(data: bytes, max_long_side: int = 1400) -> bytes:
    """Re-encode an image smaller before embedding.

    _fit_image only scales the DISPLAY box; ReportLab still embeds the original
    bytes. Eight full-resolution heatmaps produced a 21MB flow report, which is
    too large to email. Shrinking the payload costs nothing visible at print size.
    """
    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            if max(img.size) <= max_long_side:
                return data
            scale = max_long_side / float(max(img.size))
            resized = img.resize(
                (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                PILImage.LANCZOS,
            )
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=82, optimize=True)
            return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 - fall back to the original bytes
        logger.warning("Could not downscale a report image: %s", exc)
        return data


def _metric_table(rows: list[tuple[str, str]]) -> Table:
    table = Table([[k, v] for k, v in rows], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), BRAND_NAVY),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BRAND_LINE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _header(story: list, st: dict, title: str, subtitle: str) -> None:
    story.append(Paragraph("DESIGNEYE &middot; PREDICTIVE ATTENTION REPORT", st["small"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(title, st["title"]))
    story.append(Paragraph(subtitle, st["sub"]))
    story.append(Table([[""]], colWidths=[CONTENT_W], rowHeights=[1.2], style=TableStyle(
        [("BACKGROUND", (0, 0), (-1, -1), BRAND_INDIGO)])))
    story.append(Spacer(1, 10))


def _focus_table(focus_nodes: list[dict[str, Any]]) -> Table:
    data = [["#", "X", "Y", "Predicted intensity"]]
    for node in focus_nodes:
        data.append([
            str(node.get("rank", "")), str(node.get("x", "")), str(node.get("y", "")),
            f"{float(node.get('intensity', 0.0)) * 100:.1f}%",
        ])
    table = Table(data, colWidths=[CONTENT_W * 0.1, CONTENT_W * 0.25,
                                   CONTENT_W * 0.25, CONTENT_W * 0.4])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _suggestions_block(story: list, st: dict, suggestions: dict[str, Any] | None) -> None:
    story.append(Paragraph("AI Design Suggestions", st["h2"]))
    if not suggestions or not suggestions.get("items"):
        story.append(Paragraph(
            "No AI suggestions were generated for this analysis. The heatmap, "
            "Clarity Score, and Focus Order above are unaffected.", st["body"]))
        return

    if suggestions.get("summary"):
        story.append(Paragraph(suggestions["summary"], st["body"]))
        story.append(Spacer(1, 8))

    for i, item in enumerate(suggestions["items"], start=1):
        sev = str(item.get("severity", "medium")).upper()
        story.append(Paragraph(
            f"<b>{i}. {item.get('title', '')}</b> "
            f"<font color='#64748B' size='8'>[{sev} &middot; "
            f"{_basis(item)}]</font>", st["body"]))
        story.append(Paragraph(item.get("detail", ""), st["body"]))
        story.append(Spacer(1, 7))


def build_result_report(asset: dict[str, Any], result: dict[str, Any],
                        heatmap_png: bytes | None,
                        suggestions: dict[str, Any] | None = None,
                        project_title: str = "",
                        filmstrip_png: bytes | None = None) -> bytes:
    """Single-mockup analysis report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title="DesignEye Analysis Report", author="DesignEye",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    st = _styles()
    story: list = []

    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    _header(story, st, asset.get("original_filename", "Untitled mockup"),
            f"{project_title or 'Project'} &middot; generated {generated}")

    story.append(Paragraph("Predicted Attention Heatmap", st["h2"]))
    if heatmap_png:
        img = _fit_image(heatmap_png, CONTENT_W, 150 * mm)
        if img is not None:
            story.append(img)
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                "JET colormap; red indicates the highest predicted attention.",
                st["small"]))
    else:
        story.append(Paragraph("Heatmap image unavailable.", st["body"]))

    story.append(Paragraph("Attention Metrics", st["h2"]))
    story.append(_metric_table([
        ("Clarity Score (0-100)", f"{result.get('clarity_score', 0):.1f}"),
        ("Focus index (attention concentration)", f"{result.get('focus_index', 0):.3f}"),
        ("Clutter index (edge density)", f"{result.get('clutter_index', 0):.3f}"),
        ("Inference time", f"{result.get('inference_time_ms', 0)} ms"),
        ("Mockup dimensions", f"{asset.get('width', 0)} x {asset.get('height', 0)} px"),
    ]))

    story.append(Paragraph("Predicted Focus Order", st["h2"]))
    story.append(Paragraph(
        "Ranked fixation points in original image pixel coordinates.", st["small"]))
    story.append(Spacer(1, 5))
    story.append(_focus_table(result.get("focus_nodes", [])))

    region = result.get("region_saliency") or {}
    if region:
        story.append(Paragraph("Regional Attention Distribution", st["h2"]))
        keys = ["top_left", "top_center", "top_right", "mid_left", "mid_center",
                "mid_right", "bot_left", "bot_center", "bot_right"]
        grid = [[f"{region.get(keys[r * 3 + c], 0.0):.3f}" for c in range(3)]
                for r in range(3)]
        table = Table(grid, colWidths=[CONTENT_W / 3] * 3)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, BRAND_LINE),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (-1, -1), BRAND_NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(table)

    if filmstrip_png:
        story.append(PageBreak())
        story.append(Paragraph("Predicted Viewing Order", st["h2"]))
        story.append(Paragraph(
            "Frames from the replay, earliest first. The circled marker is the "
            "predicted point of gaze; numbered dots are the stops reached so far.",
            st["small"]))
        story.append(Spacer(1, 6))
        strip = _fit_image(filmstrip_png, CONTENT_W, 205 * mm)
        if strip is not None:
            story.append(strip)
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "This is a simulation, not a recording. The model predicts where "
            "people are most likely to look; the order shown is strongest-first, "
            "with pause lengths taken from published eye-tracking research. Real "
            "viewers will not follow this exact route.", st["small"]))

    story.append(PageBreak())
    _suggestions_block(story, st, suggestions)
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Predictions come from a SalGAN-style saliency model and estimate where "
        "viewers are likely to look. They are not a substitute for testing with "
        "real users.", st["small"]))

    doc.build(story)
    return buf.getvalue()


def build_comparison_report(comparison: dict[str, Any], side_a: dict[str, Any],
                            side_b: dict[str, Any], heatmap_a: bytes | None,
                            heatmap_b: bytes | None) -> bytes:
    """A/B comparison report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title="DesignEye A/B Comparison", author="DesignEye",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    st = _styles()
    story: list = []

    delta = float(comparison.get("clarity_delta", 0.0))
    winner = "Design A" if delta > 0 else ("Design B" if delta < 0 else "Tie")
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    _header(story, st, "A/B Clarity Comparison", f"Generated {generated}")

    story.append(_metric_table([
        ("Design A Clarity Score",
         f"{side_a.get('result', {}).get('clarity_score', 0):.1f}"),
        ("Design B Clarity Score",
         f"{side_b.get('result', {}).get('clarity_score', 0):.1f}"),
        ("Clarity delta (A - B)", f"{delta:+.1f} points"),
        ("Recommended variant", winner),
    ]))
    story.append(Spacer(1, 10))

    for label, side, png in (("Design A", side_a, heatmap_a),
                             ("Design B", side_b, heatmap_b)):
        asset = side.get("asset", {})
        result = side.get("result", {})
        story.append(Paragraph(
            f"{label} &mdash; {asset.get('original_filename', 'Untitled')}", st["h2"]))
        if png:
            img = _fit_image(png, CONTENT_W, 105 * mm)
            if img is not None:
                story.append(img)
                story.append(Spacer(1, 6))
        story.append(_metric_table([
            ("Clarity Score", f"{result.get('clarity_score', 0):.1f}"),
            ("Focus index", f"{result.get('focus_index', 0):.3f}"),
            ("Clutter index", f"{result.get('clutter_index', 0):.3f}"),
        ]))
        story.append(Spacer(1, 12))

    doc.build(story)
    return buf.getvalue()


def build_flow_report(batch: dict[str, Any], screens: list[dict[str, Any]],
                      heatmaps: dict[str, bytes] | None = None) -> bytes:
    """Combined report for a multi-screen flow.

    One document covering the whole journey: the flow-level reading first, a
    clarity-across-screens table, then a page per screen.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title="DesignEye Flow Report", author="DesignEye",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    st = _styles()
    story: list = []
    heatmaps = heatmaps or {}

    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    _header(story, st, batch.get("source_filename", "Design flow"),
            f"{len(screens)} screens &middot; generated {generated}")

    scored = [s for s in screens if s.get("clarity_score") is not None]
    average = (sum(float(s["clarity_score"]) for s in scored) / len(scored)) if scored else 0.0

    story.append(Paragraph("Across the whole flow", st["h2"]))
    story.append(_metric_table([
        ("Screens analysed", f"{len(scored)} of {len(screens)}"),
        ("Average Clarity Score", f"{average:.1f}"),
        ("Weakest screen", str(batch.get("weakest_screen") or "-")),
        ("Strongest screen", str(batch.get("strongest_screen") or "-")),
    ]))

    if batch.get("flow_summary"):
        story.append(Spacer(1, 10))
        story.append(Paragraph(batch["flow_summary"], st["body"]))

    # Clarity per screen, so the drop-off is visible at a glance.
    story.append(Paragraph("Clarity by screen", st["h2"]))
    rows = [["Screen", "Clarity", "Focus", "Clutter", "Status"]]
    for screen in screens:
        score = screen.get("clarity_score")
        rows.append([
            str(screen.get("page_number", "")),
            f"{float(score):.1f}" if score is not None else "-",
            f"{float(screen.get('focus_index') or 0):.3f}",
            f"{float(screen.get('clutter_index') or 0):.3f}",
            str(screen.get("status", "")),
        ])
    table = Table(rows, colWidths=[CONTENT_W * 0.14, CONTENT_W * 0.2,
                                   CONTENT_W * 0.2, CONTENT_W * 0.2, CONTENT_W * 0.26])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    for screen in screens:
        story.append(PageBreak())
        number = screen.get("page_number", "?")
        score = screen.get("clarity_score")
        story.append(Paragraph(f"Screen {number}", st["h2"]))
        story.append(Paragraph(
            f"Clarity {float(score):.1f}/100" if score is not None
            else "Not analysed", st["small"]))

        png = heatmaps.get(screen.get("asset_id", ""))
        if png:
            img = _fit_image(_downscale_png(png), CONTENT_W, 135 * mm)
            if img is not None:
                story.append(Spacer(1, 6))
                story.append(img)

        if screen.get("headline"):
            story.append(Spacer(1, 8))
            story.append(Paragraph(screen["headline"], st["body"]))

        for i, item in enumerate(screen.get("suggestions") or [], start=1):
            sev = str(item.get("severity", "medium")).upper()
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"<b>{i}. {item.get('title', '')}</b> "
                f"<font color='#64748B' size='8'>[{sev} &middot; "
                f"{_basis(item)}]</font>", st["body"]))
            story.append(Paragraph(item.get("detail", ""), st["body"]))

    doc.build(story)
    return buf.getvalue()

