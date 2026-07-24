"""Extract standardized financial figures from EDGAR XBRL ``companyfacts`` data.

XBRL tags financial statement line items with standardized ``us-gaap`` concept
names, which makes extraction far more reliable than parsing HTML tables. For a
curated set of concepts we pick, for each concept, the most recent annual (FY)
and most recent quarterly value whose period end is on or before the cutoff date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# Curated concepts: (list of us-gaap tags in preference order) -> friendly label.
# The first tag that has data for the company/period is used. This map is the one
# place to broaden coverage.
CONCEPTS: list[tuple[list[str], str]] = [
    (["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
      "SalesRevenueNet"], "Revenue"),
    (["CostOfRevenue", "CostOfGoodsAndServicesSold"], "Cost of Revenue"),
    (["GrossProfit"], "Gross Profit"),
    (["OperatingIncomeLoss"], "Operating Income"),
    (["ResearchAndDevelopmentExpense"], "R&D Expense"),
    (["SellingGeneralAndAdministrativeExpense"], "SG&A Expense"),
    (["NetIncomeLoss", "ProfitLoss"], "Net Income"),
    (["EarningsPerShareBasic"], "EPS (Basic)"),
    (["EarningsPerShareDiluted"], "EPS (Diluted)"),
    (["Assets"], "Total Assets"),
    (["AssetsCurrent"], "Current Assets"),
    (["Liabilities"], "Total Liabilities"),
    (["LiabilitiesCurrent"], "Current Liabilities"),
    (["StockholdersEquity",
      "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
     "Stockholders' Equity"),
    (["CashAndCashEquivalentsAtCarryingValue"], "Cash & Equivalents"),
    (["LongTermDebtNoncurrent", "LongTermDebt"], "Long-Term Debt"),
    (["NetCashProvidedByUsedInOperatingActivities"], "Operating Cash Flow"),
    (["PaymentsToAcquirePropertyPlantAndEquipment"], "CapEx"),
]

ANNUAL = "FY"
QUARTERS = {"Q1", "Q2", "Q3", "Q4"}
# Preferred XBRL units in order; the first present wins for a concept.
_UNIT_PREFERENCE = ["USD", "USD/shares", "shares", "pure"]


@dataclass(frozen=True)
class Figure:
    concept: str          # the us-gaap tag actually used
    label: str            # friendly label
    period_end: date
    fiscal_period: str     # "FY" or "Q1".."Q4"
    fiscal_year: Optional[int]
    value: float
    unit: str
    form: str
    accession: str


def _best_fact(units: dict, cutoff: date, kind: str) -> Optional[dict]:
    """Return the most recent fact of ``kind`` ('annual'|'quarterly') at or before
    the cutoff, tagged with the unit it was found under."""
    best: Optional[dict] = None
    best_end: Optional[date] = None

    ordered_units = [u for u in _UNIT_PREFERENCE if u in units]
    ordered_units += [u for u in units if u not in ordered_units]

    for unit in ordered_units:
        for fact in units[unit]:
            fp = fact.get("fp")
            if kind == "annual" and fp != ANNUAL:
                continue
            if kind == "quarterly" and fp not in QUARTERS:
                continue
            end_raw = fact.get("end")
            if not end_raw:
                continue
            try:
                end = date.fromisoformat(end_raw)
            except ValueError:
                continue
            if end > cutoff:
                continue
            if best_end is None or end > best_end:
                best = {**fact, "_unit": unit}
                best_end = end
        # If a preferred unit produced a match, keep scanning only that unit's
        # siblings is unnecessary; but continuing lets a better period from a
        # later unit win, which is fine because value semantics match by concept.
    return best


def extract_figures(company_facts: dict, cutoff_date: date) -> list[Figure]:
    """Pull the curated figures from ``companyfacts`` JSON."""
    us_gaap = company_facts.get("facts", {}).get("us-gaap", {})
    figures: list[Figure] = []

    for tags, label in CONCEPTS:
        for kind in ("annual", "quarterly"):
            fact = None
            used_tag = None
            for tag in tags:
                concept = us_gaap.get(tag)
                if not concept:
                    continue
                units = concept.get("units", {})
                fact = _best_fact(units, cutoff_date, kind)
                if fact is not None:
                    used_tag = tag
                    break
            if fact is None or used_tag is None:
                continue

            end = date.fromisoformat(fact["end"])
            figures.append(
                Figure(
                    concept=used_tag,
                    label=label,
                    period_end=end,
                    fiscal_period=fact.get("fp", ""),
                    fiscal_year=fact.get("fy"),
                    value=float(fact["val"]),
                    unit=fact["_unit"],
                    form=fact.get("form", ""),
                    accession=fact.get("accn", ""),
                )
            )

    return figures
