import os

import pytest

from financescrape.pdf_export import PdfExportError, save_prompt_pdf

pytest.importorskip("reportlab")


def test_pdf_written_and_valid(tmp_path):
    out = tmp_path / "prompt.pdf"
    text = "## Item 1A. Risk Factors\n\nSupply chain risk & <competition>.\n\n## Item 7\n\nRevenue grew."
    save_prompt_pdf(text, str(out), title="Test & Co Analysis")
    assert out.exists()
    with open(out, "rb") as fh:
        assert fh.read(5) == b"%PDF-"
    assert os.path.getsize(out) > 0
