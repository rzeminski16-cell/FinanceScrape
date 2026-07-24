"""Select the relevant filings from an EDGAR submissions payload.

The rule (per the app's requirements): for each requested form type, take the
single most recent filing whose ``filingDate`` is on or before the user's cutoff
date. A filing dated exactly on the cutoff is included; anything after it is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

DEFAULT_FORMS = ("10-K", "10-Q", "8-K")

ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{doc}"
ARCHIVE_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/"


@dataclass(frozen=True)
class Filing:
    form: str
    filing_date: date
    report_date: Optional[date]
    accession_number: str
    primary_document: str
    cik: str  # 10-digit padded

    @property
    def _accn_nodash(self) -> str:
        return self.accession_number.replace("-", "")

    @property
    def document_url(self) -> str:
        cik_int = int(self.cik)
        if self.primary_document:
            return ARCHIVE_DOC_URL.format(
                cik_int=cik_int, accn_nodash=self._accn_nodash, doc=self.primary_document
            )
        return ARCHIVE_INDEX_URL.format(cik_int=cik_int, accn_nodash=self._accn_nodash)


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _iter_recent_filings(submissions: dict, cik10: str) -> Iterable[Filing]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accns = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    n = len(forms)
    for i in range(n):
        fdate = _parse_date(filing_dates[i]) if i < len(filing_dates) else None
        if fdate is None:
            continue
        yield Filing(
            form=forms[i],
            filing_date=fdate,
            report_date=_parse_date(report_dates[i]) if i < len(report_dates) else None,
            accession_number=accns[i] if i < len(accns) else "",
            primary_document=primary_docs[i] if i < len(primary_docs) else "",
            cik=cik10,
        )


def select_filings(
    submissions: dict,
    cutoff_date: date,
    forms: Iterable[str] = DEFAULT_FORMS,
) -> dict[str, Optional[Filing]]:
    """Return a mapping of form -> most recent Filing on or before ``cutoff_date``.

    Forms with no qualifying filing map to ``None``.
    """
    cik10 = str(submissions.get("cik", "")).zfill(10)
    wanted = list(forms)
    best: dict[str, Optional[Filing]] = {f: None for f in wanted}

    for filing in _iter_recent_filings(submissions, cik10):
        if filing.form not in best:
            continue
        if filing.filing_date > cutoff_date:
            continue
        current = best[filing.form]
        if current is None or filing.filing_date > current.filing_date:
            best[filing.form] = filing

    return best
