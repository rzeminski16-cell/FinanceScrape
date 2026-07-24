from financescrape.prompt_builder import build_prompt
from financescrape.sections import Section, extract_sections

SAMPLE_10K = """
<html><body>
<table>
  <tr><td>Item 1. Business</td><td>3</td></tr>
  <tr><td>Item 1A. Risk Factors</td><td>10</td></tr>
  <tr><td>Item 7. Management's Discussion and Analysis</td><td>30</td></tr>
</table>
<h2>Item 1. Business</h2>
<p>We design and sell consumer electronics and services worldwide.</p>
<p>Our products include phones, computers and wearables.</p>
<h2>Item 1A. Risk Factors</h2>
<p>Our business is subject to macroeconomic risks and supply chain disruption.</p>
<p>Competition is intense across all markets we serve.</p>
<h2>Item 7. Management's Discussion and Analysis</h2>
<p>Revenue increased during the fiscal year driven by strong demand.</p>
</body></html>
"""


def test_extract_items_and_pick_body_over_toc():
    sections = extract_sections(SAMPLE_10K)
    titles = [s.title for s in sections]
    assert any("Item 1A" in t for t in titles)
    assert any("Item 7" in t for t in titles)

    risk = next(s for s in sections if s.title.startswith("Item 1A"))
    # The body occurrence (with real text) should be chosen over the TOC entry.
    assert "macroeconomic risks" in risk.text


def test_sections_ordered_by_item_number():
    sections = extract_sections(SAMPLE_10K)
    keys = [s.title.split(".")[0] for s in sections]
    assert keys == ["Item 1", "Item 1A", "Item 7"]


def test_empty_html_returns_empty():
    assert extract_sections("") == []


def test_prompt_includes_selected_sections():
    sections = [
        Section("[10-K] Item 1A. Risk Factors", "Supply chain risk."),
        Section("[10-K] Item 7. MD&A", "Revenue grew."),
    ]
    prompt = build_prompt("Acme Inc", sections)
    assert "Acme Inc" in prompt
    assert "Item 1A. Risk Factors" in prompt
    assert "Supply chain risk." in prompt
    assert "Revenue grew." in prompt
    # Includes the analyst closing instructions.
    assert "follow-up questions" in prompt


def test_prompt_handles_no_sections():
    prompt = build_prompt("Acme Inc", [])
    assert "No sections were selected" in prompt
