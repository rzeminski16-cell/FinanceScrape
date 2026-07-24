# FinanceScrape

A small desktop app that scrapes the SEC's EDGAR system for a company's filings
as of a chosen date, then produces:

1. **An Excel dashboard** of standardized financial figures (revenue, net income,
   assets, cash flow, EPS, computed ratios, …) pulled from the filings' XBRL data.
2. **A ChatGPT analysis prompt** built from the filing sections you select
   (Item 1A Risk Factors, Item 7 MD&A, …), ready to paste into ChatGPT.

You enter a **ticker or company name** and a **cutoff date**. For each of the
`10-K`, `10-Q`, and `8-K` forms, the app takes the most recent filing dated **on
or before** that date (never after).

## Install

Requires **Python 3.9+** with Tkinter (Tkinter ships with most Python installs;
on Debian/Ubuntu install it with `sudo apt-get install python3-tk`).

```bash
pip install -r requirements.txt
```

## Run

```bash
python -m financescrape.main
```

1. **Tab 1 — Fetch & Dashboard:** enter the ticker/name, cutoff date, and your
   contact email, choose where to save the workbook, and click *Fetch*. If the
   name matches several companies you'll be asked to pick one. The dashboard is
   written as an `.xlsx` with three sheets: **Summary** (matched filings),
   **Key Figures** (metrics + ratios), and **Raw Facts** (full extracted table).
2. **Tab 2 — Analysis Prompt:** tick the 10-K / 10-Q sections you care about,
   click *Build prompt*, then *Copy* or *Save .txt* to use it in ChatGPT.

## SEC contact email (required)

SEC EDGAR requires every request to carry a `User-Agent` header with a real
contact email, and returns `403 Forbidden` without one. The app prefills the
email field but you can change it. This is a SEC policy, not an account login —
no credentials are involved.

## How it works

| Module | Responsibility |
| --- | --- |
| `edgar_client.py` | Polite HTTP client (User-Agent, throttling, retries); ticker→CIK, submissions, company facts, document fetch |
| `filings.py` | Selects the latest `10-K`/`10-Q`/`8-K` on or before the cutoff date |
| `financials.py` | Extracts standardized figures from XBRL `companyfacts` data |
| `dashboard.py` | Builds the multi-sheet Excel workbook (openpyxl) |
| `sections.py` | Parses 10-K/10-Q HTML into selectable Item/section headers + text |
| `prompt_builder.py` | Formats selected sections into a ChatGPT analysis prompt |
| `app.py` / `main.py` | Tkinter GUI and entry point |

Financial figures come from EDGAR's structured **XBRL** data rather than parsed
HTML tables, which gives standardized field names across companies. Coverage
depends on how a company tags its XBRL; the `CONCEPTS` list in `financials.py` is
the single place to add more metrics.

## Tests

```bash
pip install pytest
python -m pytest
```

Tests cover the date-boundary filing selection, XBRL figure extraction, HTML
section parsing, and prompt building — all offline with fixtures. The live SEC
network path is exercised at runtime by the app.

## Notes

- Section selection applies to the `10-K` and `10-Q` (which use standardized
  numbered Items). `8-K`s are included in the filing list and dashboard but are
  not standardized for section extraction.
- Data is sourced from public SEC EDGAR APIs; no login or API key is needed.
