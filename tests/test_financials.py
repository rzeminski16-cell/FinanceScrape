from datetime import date

from financescrape.financials import extract_figures

FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {"end": "2020-12-31", "val": 100, "fy": 2020, "fp": "FY", "form": "10-K", "accn": "a-20"},
                        {"end": "2021-12-31", "val": 120, "fy": 2021, "fp": "FY", "form": "10-K", "accn": "a-21"},
                        {"end": "2022-12-31", "val": 150, "fy": 2022, "fp": "FY", "form": "10-K", "accn": "a-22"},
                        {"end": "2022-03-31", "val": 35, "fy": 2022, "fp": "Q1", "form": "10-Q", "accn": "q-22"},
                    ]
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income",
                "units": {
                    "USD": [
                        {"end": "2021-12-31", "val": 20, "fy": 2021, "fp": "FY", "form": "10-K", "accn": "a-21"},
                    ]
                },
            },
            "EarningsPerShareDiluted": {
                "label": "EPS diluted",
                "units": {
                    "USD/shares": [
                        {"end": "2021-12-31", "val": 1.25, "fy": 2021, "fp": "FY", "form": "10-K", "accn": "a-21"},
                    ]
                },
            },
        }
    }
}


def _by_label_period(figures):
    return {(f.label, f.fiscal_period): f for f in figures}


def test_annual_respects_cutoff():
    figures = extract_figures(FACTS, date(2021, 12, 31))
    idx = _by_label_period(figures)
    # Latest annual on/before 2021-12-31 is FY2021 (=120), not FY2022.
    assert idx[("Revenue", "FY")].value == 120
    assert idx[("Revenue", "FY")].fiscal_year == 2021


def test_annual_picks_latest_when_cutoff_later():
    figures = extract_figures(FACTS, date(2023, 6, 30))
    idx = _by_label_period(figures)
    assert idx[("Revenue", "FY")].value == 150
    assert idx[("Revenue", "FY")].fiscal_year == 2022


def test_quarterly_extracted():
    figures = extract_figures(FACTS, date(2022, 6, 30))
    idx = _by_label_period(figures)
    assert idx[("Revenue", "Q1")].value == 35


def test_unit_and_eps_captured():
    figures = extract_figures(FACTS, date(2022, 1, 1))
    idx = _by_label_period(figures)
    eps = idx[("EPS (Diluted)", "FY")]
    assert eps.value == 1.25
    assert eps.unit == "USD/shares"


def test_missing_concepts_are_skipped():
    figures = extract_figures({"facts": {"us-gaap": {}}}, date(2022, 1, 1))
    assert figures == []
