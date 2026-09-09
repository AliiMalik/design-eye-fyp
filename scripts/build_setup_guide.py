"""One-page setup sheet for teammates cloning DesignEye."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path("D:/FYP/designeye project/designeye/backend")
sys.path.insert(0, str(BACKEND))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

NAVY = colors.HexColor("#1B2559")
INDIGO = colors.HexColor("#4F5BD5")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
CODEBG = colors.HexColor("#F1F5F9")
AMBER = colors.HexColor("#B45309")

PAGE_W, PAGE_H = A4
MARGIN = 13 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

S = {
    "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17,
                            textColor=NAVY, spaceAfter=1, leading=20),
    "sub": ParagraphStyle("s", fontName="Helvetica", fontSize=8.2,
                          textColor=MUTED, spaceAfter=6, leading=11),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=9.6,
                         textColor=NAVY, spaceBefore=6, spaceAfter=3, leading=12),
    "body": ParagraphStyle("b", fontName="Helvetica", fontSize=8.2,
                           leading=11, textColor=colors.HexColor("#1E293B")),
    "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=7.3,
                            leading=9.5, textColor=MUTED),
    "code": ParagraphStyle("c", fontName="Courier-Bold", fontSize=8,
                           leading=11, textColor=NAVY),
    "warn": ParagraphStyle("w", fontName="Helvetica", fontSize=7.8,
                           leading=10.5, textColor=AMBER),
}


def code(cmd: str) -> Table:
    t = Table([[Paragraph(cmd, S["code"])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODEBG),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBEFORE", (0, 0), (0, -1), 2, INDIGO),
    ]))
    return t


def step(n: str, title: str, blocks: list) -> KeepTogether:
    head = Table(
        [[Paragraph(f"<b>{n}</b>", ParagraphStyle(
            "n", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white,
            alignment=1)),
          Paragraph(f"<b>{title}</b>", S["h2"])]],
        colWidths=[7 * mm, CONTENT_W - 7 * mm])
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), INDIGO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return KeepTogether([head, Spacer(1, 2), *blocks, Spacer(1, 4)])


def build(out: Path, repo_url: str) -> None:
    doc = SimpleDocTemplate(
        str(out), pagesize=A4, title="DesignEye - Setup Guide",
        author="DesignEye", leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=11 * mm, bottomMargin=9 * mm,
    )
    st: list = []

    st.append(Paragraph("DesignEye &mdash; Run it on any laptop", S["title"]))
    st.append(Paragraph(
        "Clone, configure, start. About 15 minutes, most of it Docker downloading images.",
        S["sub"]))
    st.append(Table([[""]], colWidths=[CONTENT_W], rowHeights=[1.4],
                    style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), INDIGO)])))
    st.append(Spacer(1, 6))

    # --- 0 prerequisites ---
    pre = Table(
        [[Paragraph("<b>Docker Desktop</b><br/>docker.com/products/docker-desktop", S["small"]),
          Paragraph("<b>Git</b><br/>git-scm.com", S["small"]),
          Paragraph("<b>The model file</b><br/>ask Ali (~99&nbsp;MB, not on GitHub)", S["small"])]],
        colWidths=[CONTENT_W / 3] * 3)
    pre.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    st.append(step("0", "Install these first", [pre]))

    # --- 1 clone ---
    st.append(step("1", "Clone the repository", [code(f"git clone {repo_url}")]))
    st.append(step("1b", "", [code("cd designeye")]))
    st.pop()  # merge 1b into 1 visually
    st[-1] = step("1", "Clone the repository", [
        code(f"git clone {repo_url}"), Spacer(1, 2), code("cd designeye")])

    # --- 2 weights ---
    st.append(step("2", "Add the model file", [
        Paragraph(
            "The trained model is 99&nbsp;MB, so GitHub does not carry it. Ali will send "
            "<font face='Courier'>stage3_ui_best_val.pth</font>. Put it here exactly:", S["body"]),
        Spacer(1, 2),
        code("backend/app/ml/weights/stage3_ui_best_val.pth"),
        Spacer(1, 2),
        Paragraph("Without this the app starts but every upload fails.", S["warn"]),
    ]))

    # --- 3 env ---
    st.append(step("3", "Create your settings file", [
        Paragraph("Copy the template, then generate a login secret:", S["body"]),
        Spacer(1, 2),
        code("cp .env.example .env"),
        Spacer(1, 2),
        code("python -c \"import secrets;print(secrets.token_urlsafe(48))\""),
        Spacer(1, 2),
        Paragraph(
            "Paste that output as <font face='Courier'>JWT_SECRET=</font> inside "
            "<font face='Courier'>.env</font>. Leave everything else as it is &mdash; the "
            "defaults run fully offline with no accounts or API keys.", S["body"]),
        Paragraph(
            "On Windows use <font face='Courier'>copy .env.example .env</font> instead of cp.",
            S["small"]),
    ]))

    # --- 4 start ---
    st.append(step("4", "Start everything", [
        code("docker compose up -d --build"),
        Spacer(1, 2),
        Paragraph(
            "First run takes 5&ndash;10 minutes: it downloads Python, Node, MongoDB and Redis, "
            "and installs PyTorch. Later runs take seconds.", S["body"]),
    ]))

    # --- 5 seed ---
    st.append(step("5", "Create the demo account", [
        code("docker compose exec api python -m app.seed --reset"),
    ]))

    # --- 6 open ---
    open_tbl = Table(
        [[Paragraph("<b>Web app</b>", S["small"]), Paragraph("http://localhost:3000", S["code"])],
         [Paragraph("<b>Email</b>", S["small"]), Paragraph("demo@designeye.app", S["code"])],
         [Paragraph("<b>Password</b>", S["small"]), Paragraph("Demo@1234", S["code"])],
         [Paragraph("<b>API docs</b>", S["small"]), Paragraph("http://localhost:8000/docs", S["code"])]],
        colWidths=[24 * mm, CONTENT_W - 24 * mm])
    open_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    st.append(step("6", "Open it and sign in", [open_tbl]))

    # --- checks ---
    st.append(Spacer(1, 3))
    st.append(Paragraph("Check it actually works", S["h2"]))
    checks = Table([
        [Paragraph("Everything healthy?", S["small"]),
         Paragraph("open http://localhost:8000/health &mdash; model_loaded must be true", S["small"])],
        [Paragraph("Run the tests", S["small"]),
         Paragraph("docker compose exec api python -m pytest -q", S["code"])],
    ], colWidths=[34 * mm, CONTENT_W - 34 * mm])
    checks.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    st.append(checks)

    # --- troubleshooting ---
    st.append(Spacer(1, 5))
    st.append(Paragraph("If something goes wrong", S["h2"]))
    tr = Table([
        [Paragraph("<b>Problem</b>", S["small"]), Paragraph("<b>Fix</b>", S["small"])],
        [Paragraph("model_loaded is false", S["small"]),
         Paragraph("The .pth file is missing or in the wrong folder. Re-check step 2.", S["small"])],
        [Paragraph("Port already in use", S["small"]),
         Paragraph("Something else is on 3000, 8000 or 27017. Close it, or edit the ports in docker-compose.yml.", S["small"])],
        [Paragraph("redis is false", S["small"]),
         Paragraph("Normal. DEV_MODE runs analysis inline, so Redis is not needed.", S["small"])],
        [Paragraph("Changed code, nothing happened", S["small"]),
         Paragraph("Code is baked into the image. Restart is not enough &mdash; rebuild: docker compose build api worker frontend, then up -d.", S["small"])],
        [Paragraph("Want to start over", S["small"]),
         Paragraph("docker compose down -v wipes the database, then repeat steps 4 and 5.", S["small"])],
    ], colWidths=[38 * mm, CONTENT_W - 38 * mm])
    tr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    st.append(tr)

    # --- footer ---
    st.append(Spacer(1, 6))
    st.append(Table([[""]], colWidths=[CONTENT_W], rowHeights=[0.6],
                    style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), LINE)])))
    st.append(Spacer(1, 3))
    st.append(Paragraph(
        "<b>Understanding the code:</b> start with docs/CODE_WALKTHROUGH.md &mdash; it is written "
        "to be read with the code open beside it. docs/DEVIATIONS.md explains why anything "
        "differs from the SDS. &nbsp;&bull;&nbsp; DesignEye, Final Year Project, Group S26CS003, "
        "University of Central Punjab.", S["small"]))

    doc.build(st)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/&lt;your-username&gt;/designeye.git"
    out = Path("D:/FYP/designeye project/designeye/docs/SETUP_GUIDE.pdf")
    build(out, url)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")
