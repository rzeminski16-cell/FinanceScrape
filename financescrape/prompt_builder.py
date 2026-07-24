"""Turn selected filing sections into a ready-to-paste ChatGPT analysis prompt."""

from __future__ import annotations

from typing import Iterable

from .sections import Section

_LEAD_IN = (
    "You are an experienced financial analyst. Below are selected sections from "
    "{company}'s SEC filing{form_note}. Read them carefully and help me analyze "
    "the company."
)

_CLOSING = (
    "\n\n---\n\nUsing only the sections above, please:\n"
    "1. Summarize the key points of each section in plain language.\n"
    "2. Identify the most important risks, trends, and changes.\n"
    "3. Flag anything that looks unusual, concerning, or notably positive.\n"
    "4. Suggest follow-up questions I should investigate.\n"
    "Be specific and cite the section titles you draw from."
)


def build_prompt(
    company: str,
    selected_sections: Iterable[Section],
    form: str | None = None,
) -> str:
    sections = list(selected_sections)
    form_note = f" ({form})" if form else ""
    parts = [_LEAD_IN.format(company=company or "the company", form_note=form_note)]

    if not sections:
        parts.append("\n\n(No sections were selected.)")
        return "".join(parts)

    for section in sections:
        body = section.text.strip()
        parts.append(f"\n\n## {section.title}\n\n{body}")

    parts.append(_CLOSING)
    return "".join(parts)
