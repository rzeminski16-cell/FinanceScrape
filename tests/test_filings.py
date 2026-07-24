from datetime import date

from financescrape.filings import select_filings

SUBMISSIONS = {
    "cik": 320193,
    "filings": {
        "recent": {
            "form": ["10-K", "10-Q", "10-Q", "8-K", "10-K", "8-K"],
            "filingDate": [
                "2022-10-28",  # 10-K (after typical cutoff)
                "2022-07-29",  # 10-Q
                "2022-01-28",  # 10-Q (earlier)
                "2022-08-01",  # 8-K
                "2021-10-29",  # 10-K (older)
                "2023-02-02",  # 8-K after cutoff
            ],
            "reportDate": [
                "2022-09-24", "2022-06-25", "2021-12-25",
                "2022-08-01", "2021-09-25", "2023-02-02",
            ],
            "accessionNumber": [
                "0000320193-22-000108",
                "0000320193-22-000070",
                "0000320193-22-000007",
                "0000320193-22-000071",
                "0000320193-21-000105",
                "0000320193-23-000005",
            ],
            "primaryDocument": [
                "aapl-20220924.htm", "aapl-20220625.htm", "aapl-20211225.htm",
                "d1.htm", "aapl-20210925.htm", "d2.htm",
            ],
        }
    },
}


def test_latest_of_each_type_before_cutoff():
    result = select_filings(SUBMISSIONS, date(2022, 12, 31))
    assert result["10-K"].filing_date == date(2022, 10, 28)
    assert result["10-Q"].filing_date == date(2022, 7, 29)
    assert result["8-K"].filing_date == date(2022, 8, 1)  # not the 2023 one


def test_boundary_inclusive_on_exact_date():
    # Cutoff exactly on a 10-K filing date includes it.
    result = select_filings(SUBMISSIONS, date(2022, 10, 28))
    assert result["10-K"].filing_date == date(2022, 10, 28)
    # Day before excludes it, falling back to the older 10-K.
    result2 = select_filings(SUBMISSIONS, date(2022, 10, 27))
    assert result2["10-K"].filing_date == date(2021, 10, 29)


def test_missing_type_returns_none():
    result = select_filings(SUBMISSIONS, date(2010, 1, 1))
    assert result["10-K"] is None
    assert result["10-Q"] is None
    assert result["8-K"] is None


def test_document_url_construction():
    result = select_filings(SUBMISSIONS, date(2022, 12, 31))
    tenk = result["10-K"]
    assert tenk.document_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019322000108/aapl-20220924.htm"
    )
