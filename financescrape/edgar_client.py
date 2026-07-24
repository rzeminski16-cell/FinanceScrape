"""HTTP client for the SEC EDGAR APIs.

The SEC requires every request to carry a descriptive ``User-Agent`` header that
includes a contact email; unidentified traffic is answered with ``403``. The
public APIs are also rate limited to roughly 10 requests/second, so this client
throttles itself and retries on transient failures.

Endpoints used:
  * Ticker -> CIK map : https://www.sec.gov/files/company_tickers.json
  * Filing history    : https://data.sec.gov/submissions/CIK##########.json
  * XBRL company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
  * Filing documents  : https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{doc}
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"

# SEC asks callers to stay under ~10 requests/second.
_MIN_INTERVAL_SECONDS = 0.12
_MAX_RETRIES = 4


@dataclass(frozen=True)
class CompanyMatch:
    """A resolved company from the ticker/name lookup."""

    cik: str  # zero-padded, 10 digits
    ticker: str
    name: str


class EdgarError(RuntimeError):
    """Raised when EDGAR cannot satisfy a request."""


class EdgarClient:
    """A small, polite EDGAR HTTP client."""

    def __init__(self, user_agent_email: str, app_name: str = "FinanceScrape"):
        email = (user_agent_email or "").strip()
        if not email or "@" not in email:
            raise ValueError(
                "A contact email is required for the SEC User-Agent header "
                "(e.g. 'you@example.com'). SEC returns 403 without it."
            )
        self.user_agent = f"{app_name} ({email})"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request_ts = 0.0
        self._tickers_cache: Optional[list[CompanyMatch]] = None

    # -- low level --------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)

    def _get(self, url: str) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            self._throttle()
            try:
                resp = self._session.get(url, timeout=30)
                self._last_request_ts = time.monotonic()
            except requests.RequestException as exc:  # network hiccup
                last_exc = exc
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                return resp
            if resp.status_code == 404:
                raise EdgarError(f"Not found (404): {url}")
            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = EdgarError(f"HTTP {resp.status_code}: {url}")
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 403:
                raise EdgarError(
                    "SEC returned 403 Forbidden. Check that your contact email "
                    "in the User-Agent is set correctly."
                )
            raise EdgarError(f"HTTP {resp.status_code}: {url}")

        raise EdgarError(f"Request failed after {_MAX_RETRIES} attempts: {url} ({last_exc})")

    def _get_json(self, url: str) -> dict:
        return self._get(url).json()

    # -- public API -------------------------------------------------------

    @staticmethod
    def pad_cik(cik) -> str:
        """Return a 10-digit zero-padded CIK string."""
        digits = "".join(ch for ch in str(cik) if ch.isdigit())
        if not digits:
            raise ValueError(f"Invalid CIK: {cik!r}")
        return digits.zfill(10)

    def _load_tickers(self) -> list[CompanyMatch]:
        if self._tickers_cache is None:
            data = self._get_json(TICKERS_URL)
            # The file is a dict keyed by an arbitrary index; each value has
            # cik_str, ticker, title.
            matches = []
            for row in data.values():
                matches.append(
                    CompanyMatch(
                        cik=self.pad_cik(row["cik_str"]),
                        ticker=str(row.get("ticker", "")).upper(),
                        name=str(row.get("title", "")),
                    )
                )
            self._tickers_cache = matches
        return self._tickers_cache

    def resolve_company(self, query: str) -> list[CompanyMatch]:
        """Resolve a ticker or company name to one or more companies.

        Ticker matches (exact, case-insensitive) are returned first and alone.
        Otherwise a case-insensitive substring match on the company name is used;
        several candidates may come back for the GUI to disambiguate.
        """
        q = (query or "").strip()
        if not q:
            raise ValueError("Please enter a ticker or company name.")

        companies = self._load_tickers()
        q_upper = q.upper()

        exact_ticker = [c for c in companies if c.ticker == q_upper]
        if exact_ticker:
            return exact_ticker

        q_lower = q.lower()
        name_matches = [c for c in companies if q_lower in c.name.lower()]
        # Prefer exact name matches at the front.
        name_matches.sort(key=lambda c: (c.name.lower() != q_lower, c.name))
        if name_matches:
            return name_matches

        raise EdgarError(f"No company found matching {query!r}.")

    def get_submissions(self, cik) -> dict:
        cik10 = self.pad_cik(cik)
        return self._get_json(SUBMISSIONS_URL.format(cik10=cik10))

    def get_company_facts(self, cik) -> dict:
        cik10 = self.pad_cik(cik)
        return self._get_json(COMPANY_FACTS_URL.format(cik10=cik10))

    def get_document_text(self, url: str) -> str:
        return self._get(url).text
