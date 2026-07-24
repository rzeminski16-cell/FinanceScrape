"""Export the generated ChatGPT prompt to a PDF file.

Uses reportlab (a pure-Python PDF library) so no system tools are required.
The import is lazy so the rest of the app runs even if reportlab isn't
installed; :func:`save_prompt_pdf` raises a clear error in that case.
"""

from __future__ import annotations

from html import escape


class PdfExportError(RuntimeError):
    """Raised when a PDF cannot be produced."""


def _require_reportlab():
    try:
        from reportlab.lib.pagesizes import letter  # noqa: F401
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        from reportlab.lib.units import inch
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise PdfExportError(
            "PDF export needs the 'reportlab' package. Install it with "
            "'pip install reportlab' (or 'pip install -r requirements.txt')."
        ) from exc
    return SimpleDocTemplate, Paragraph, Spacer, getSampleStyleSheet, letter, inch


def save_prompt_pdf(text: str, path: str, title: str = "SEC Filing Analysis Prompt") -> str:
    """Render ``text`` to a paginated PDF at ``path`` and return the path."""
    (SimpleDocTemplate, Paragraph, Spacer,
     getSampleStyleSheet, letter, inch) = _require_reportlab()

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.leading = 15
    heading = styles["Heading2"]

    doc = SimpleDocTemplate(
        path, pagesize=letter,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        title=title,
    )

    flow = [Paragraph(escape(title), styles["Title"]), Spacer(1, 12)]
    for block in text.replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            flow.append(Spacer(1, 6))
            flow.append(Paragraph(escape(block[3:].strip()), heading))
        else:
            # Preserve single newlines within a block as line breaks.
            html = escape(block).replace("\n", "<br/>")
            flow.append(Paragraph(html, body))
        flow.append(Spacer(1, 6))

    doc.build(flow)
    return path
