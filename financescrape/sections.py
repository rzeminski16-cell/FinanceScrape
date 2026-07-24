"""Extract section/chapter headers and their body text from a filing's HTML.

10-K and 10-Q filings are organized into numbered "Items" (e.g. *Item 1A. Risk
Factors*, *Item 7. Management's Discussion and Analysis*). We locate those markers
in the document's plain text and split the body between them. Each "Item" usually
appears twice — once in the table of contents and once as the real section — so
we keep, per item, the occurrence with the most text. When no Item markers are
found we fall back to HTML heading tags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

_ITEM_RE = re.compile(r"(?im)^[ \t]*(Item[ \t]+(\d+[A-Z]?)\.?)[ \t]*([^\n]*)$")
_WS_RE = re.compile(r"[ \t]+")
_BLANKS_RE = re.compile(r"\n{3,}")


@dataclass
class Section:
    title: str
    text: str

    @property
    def preview(self) -> str:
        snippet = self.text.strip().replace("\n", " ")
        return (snippet[:120] + "…") if len(snippet) > 120 else snippet


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return _BLANKS_RE.sub("\n\n", text)


def _clean_title(item_label: str, trailing: str, lines_after: list[str]) -> str:
    item_label = item_label.rstrip(".").strip()
    trailing = trailing.strip(" .:-—")
    if trailing:
        return f"{item_label}. {trailing}"
    # Title may sit on the next non-empty line.
    for ln in lines_after[:2]:
        candidate = ln.strip(" .:-—")
        if candidate and not _ITEM_RE.match(ln):
            return f"{item_label}. {candidate}"
    return item_label


def _extract_by_items(text: str) -> list[Section]:
    matches = list(_ITEM_RE.finditer(text))
    if len(matches) < 2:
        return []

    candidates: list[tuple[str, str, str]] = []  # (item_key, title, body)
    for idx, m in enumerate(matches):
        item_key = m.group(2).upper()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        lines_after = body.splitlines()
        title = _clean_title(m.group(1), m.group(3), lines_after)
        candidates.append((item_key, title, body))

    # Keep the richest occurrence per item; preserve first-seen order of the
    # chosen (body) occurrence.
    best: dict[str, tuple[str, str]] = {}
    order: list[str] = []
    for item_key, title, body in candidates:
        if item_key not in best or len(body) > len(best[item_key][1]):
            if item_key not in best:
                order.append(item_key)
            best[item_key] = (title, body)

    def sort_key(key: str):
        num = re.match(r"(\d+)([A-Z]?)", key)
        return (int(num.group(1)), num.group(2)) if num else (9999, key)

    return [Section(best[k][0], best[k][1]) for k in sorted(order, key=sort_key)]


def _extract_by_headings(html: str) -> list[Section]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    sections: list[Section] = []
    for h in headings:
        title = _WS_RE.sub(" ", h.get_text(" ")).strip()
        if not title:
            continue
        parts = []
        for sib in h.find_all_next():
            if sib.name in ("h1", "h2", "h3", "h4"):
                break
            if sib.name in ("p", "div", "li", "td"):
                txt = _WS_RE.sub(" ", sib.get_text(" ")).strip()
                if txt:
                    parts.append(txt)
            if len("\n".join(parts)) > 8000:
                break
        sections.append(Section(title, "\n".join(parts).strip()))
    return sections


def extract_sections(html: str) -> list[Section]:
    """Return the ordered sections found in a 10-K/10-Q HTML document."""
    if not html:
        return []
    text = _html_to_text(html)
    sections = _extract_by_items(text)
    if sections:
        return sections
    return _extract_by_headings(html)
