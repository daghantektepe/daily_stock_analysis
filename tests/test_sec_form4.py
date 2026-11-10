# -*- coding: utf-8 -*-
"""Offline tests for SEC Form 4 Insider Buying fetcher, event study, and screener."""

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from data_provider.sec_form4_fetcher import (
    InsiderClusterEvent,
    InsiderTransaction,
    RoutineClassifier,
    SecForm4Fetcher,
    cluster_insider_transactions,
    normalize_symbol,
    parse_bool_flag,
    parse_sec_atom_feed,
)
from src.services.sec_form4_screener import (
    format_sec_screener_report,
    score_insider_event,
    screen_us_insider_stocks,
)
from src.services.sec_form4_study import (
    compute_sample_statistics,
    format_sec_form4_study_report,
    run_sec_form4_event_study,
)


def _make_mock_zip() -> bytes:
    """Create a minimal in-memory SEC Form 3/4/5 zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # SUBMISSION.tsv (includes ISSUERCIK, DOCUMENT_TYPE 4, 4/A amendment that should be skipped)
        sub_content = (
            "ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\tISSUERNAME\tISSUERTRADINGSYMBOL\tISSUERCIK\tAFF10B5ONE\tREMARKS\n"
            "001-01\t02-MAR-2026\t01-MAR-2026\t4\tAcme Corp\tACME\t0001234567\t0\t\n"
            "001-02\t03-MAR-2026\t02-MAR-2026\t4\tAcme Corp\tACME\t0001234567\tfalse\t\n"
            "001-03\t04-MAR-2026\t02-MAR-2026\t4/A\tAcme Corp\tACME\t0001234567\t0\tAmendment\n"
            "002-01\t05-MAR-2026\t04-MAR-2026\t4\tBeta Inc\tBETA\t0009876543\ttrue\t\n"
            "003-01\t06-MAR-2026\t05-MAR-2026\t4\tGamma Inc\tGAMMA\t0005555555\t0\tPurchased in underwritten public offering\n"
        )
        z.writestr("SUBMISSION.tsv", sub_content)

        # REPORTINGOWNER.tsv
        owner_content = (
            "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
            "001-01\t1001\tJohn Doe\tOfficer\tChief Executive Officer\n"
            "001-02\t1002\tJane Smith\tOfficer\tChief Financial Officer\n"
            "001-03\t1002\tJane Smith\tOfficer\tChief Financial Officer\n"
            "002-01\t2001\tBob Routine\tDirector\tDirector\n"
            "003-01\t3001\tCharlie Offering\tOfficer\tPresident\n"
        )
        z.writestr("REPORTINGOWNER.tsv", owner_content)

        # NONDERIV_TRANS.tsv
        trans_content = (
            "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tSECURITY_TITLE\tTRANS_FORM_TYPE\n"
            "001-01\t01-MAR-2026\tP\t1000.0\t100.0\tCommon Stock\t4\n"  # ACME CEO: $100k
            "001-02\t02-MAR-2026\tP\t500.0\t100.0\tCommon Stock\t4\n"   # ACME CFO: $50k
            "001-02\t02-MAR-2026\tS\t200.0\t100.0\tCommon Stock\t4\n"   # Sale -> ignored
            "001-03\t02-MAR-2026\tP\t500.0\t100.0\tCommon Stock\t4\n"   # Amendment 4/A -> skipped!
            "002-01\t04-MAR-2026\tP\t500.0\t50.0\tCommon Stock\t4\n"    # BETA Director 10b5-1 ('true'): $25k
            "003-01\t05-MAR-2026\tP\t1000.0\t20.0\tCommon Stock\t4\n"   # Public offering -> flagged & excluded!
        )
        z.writestr("NONDERIV_TRANS.tsv", trans_content)
    return buf.getvalue()


def test_parse_quarter_tsv_and_clustering(tmp_path) -> None:
    zip_bytes = _make_mock_zip()
    mock_zip_file = tmp_path / "mock_2026q1.zip"
    mock_zip_file.write_bytes(zip_bytes)

    fetcher = SecForm4Fetcher(cache_dir=tmp_path, user_agent="DailyStockAnalysis/1.0 (contact: test@example.com)")
    events = fetcher.parse_quarter("2026q1", zip_path=mock_zip_file, min_value=10_000.0)

    # 1. ACME has 2 purchases by 2 distinct officers (CEO and CFO) within 2 days -> clustered!
    # 2. 4/A amendment was NOT counted twice.
    # 3. GAMMA public offering was excluded by default.
    # 4. BETA has 1 purchase by Director -> single, 10b5-1 parsed as True from 'true'.
    assert len(events) == 2
    acme_event = next(e for e in events if e.symbol == "ACME")
    assert acme_event.insider_count == 2
    assert acme_event.is_cluster is True
    assert acme_event.has_c_level is True
    assert acme_event.has_10b51 is False
    assert acme_event.total_value == 150_000.0
    assert acme_event.issuer_cik == "0001234567"
    assert "0001234567" in acme_event.sec_url

    beta_event = next(e for e in events if e.symbol == "BETA")
    assert beta_event.insider_count == 1
    assert beta_event.is_cluster is False
    assert beta_event.has_10b51 is True  # 'true' correctly parsed as 10b5-1
    assert beta_event.total_value == 25_000.0


def test_routine_classifier_cmp_rules() -> None:
    classifier = RoutineClassifier()
    # Insider 1 traded in March 2023, March 2024, March 2025 -> Routine in March 2026!
    classifier.add("INSIDER_ROUTINE", date(2023, 3, 10))
    classifier.add("INSIDER_ROUTINE", date(2024, 3, 12))
    classifier.add("INSIDER_ROUTINE", date(2025, 3, 15))

    # Insider 2 traded in 2023 (Jan), 2024 (Jun), 2025 (Nov) -> Opportunistic in March 2026!
    classifier.add("INSIDER_OPPORTUNISTIC", date(2023, 1, 10))
    classifier.add("INSIDER_OPPORTUNISTIC", date(2024, 6, 12))
    classifier.add("INSIDER_OPPORTUNISTIC", date(2025, 11, 15))

    # Insider 3 only traded in 2025 (less than 3 prior years) -> Unclassified
    classifier.add("INSIDER_NEW", date(2025, 3, 10))

    event_date = date(2026, 3, 20)
    assert classifier.classify("INSIDER_ROUTINE", event_date) == "routine"
    assert classifier.classify("INSIDER_OPPORTUNISTIC", event_date) == "opportunistic"
    assert classifier.classify("INSIDER_NEW", event_date) == "unclassified"


def test_scoring_and_screening() -> None:
    e_cluster = InsiderClusterEvent(
        symbol="ACME",
        company_name="Acme Corp",
        filing_date=date(2026, 3, 2),
        insider_count=2,
        officer_director_count=2,
        total_value=150_000.0,
        total_shares=1500.0,
        avg_price=100.0,
        has_c_level=True,
        is_opportunistic=True,
        is_cluster=True,
        cmp_class="opportunistic",
        has_10b51=False,
        primary_titles=["Chief Executive Officer", "Chief Financial Officer"],
        issuer_cik="0001234567",
    )
    score, reasons = score_insider_event(e_cluster)
    assert score >= 80  # 35 (cluster) + 25 (c-level) + 20 (opp) + 15 (size) = 95
    assert any("Küme Alımı" in r for r in reasons)
    assert any("C-Suite" in r for r in reasons)

    e_routine = InsiderClusterEvent(
        symbol="BETA",
        company_name="Beta Inc",
        filing_date=date(2026, 3, 5),
        insider_count=1,
        officer_director_count=1,
        total_value=25_000.0,
        total_shares=500.0,
        avg_price=50.0,
        has_c_level=False,
        is_opportunistic=False,
        is_cluster=False,
        cmp_class="routine",
        has_10b51=True,
        primary_titles=["Director"],
        issuer_cik="0009876543",
    )
    score_rot, _ = score_insider_event(e_routine)
    assert score_rot < 40

    candidates = screen_us_insider_stocks([e_routine, e_cluster], min_score=40, top_n=5)
    assert len(candidates) == 1
    assert candidates[0].symbol == "ACME"
    assert candidates[0].score == score

    text = format_sec_screener_report(candidates)
    assert "ACME (Acme Corp)" in text
    assert "python main.py --stocks ACME" in text


def test_sec_form4_event_study_with_statistics_and_dynamic_conclusions() -> None:
    from datetime import timedelta

    t0 = date(2026, 3, 2)
    fake_acme_closes = {}
    fake_spy_closes = {}

    for day_idx in range(40):
        cur_d = t0 + timedelta(days=day_idx)
        if day_idx <= 1:
            acme_px = 100.0
            spy_px = 500.0
        else:
            acme_px = 115.0
            spy_px = 525.0
        fake_acme_closes[cur_d] = acme_px
        fake_spy_closes[cur_d] = spy_px

    def _mock_history(symbol, start, end):
        if symbol == "ACME":
            return {d: px for d, px in fake_acme_closes.items() if start <= d <= end}
        if symbol == "SPY":
            return {d: px for d, px in fake_spy_closes.items() if start <= d <= end}
        return {}

    events = [
        InsiderClusterEvent(
            symbol="ACME",
            company_name="Acme Corp",
            filing_date=t0,
            insider_count=2,
            officer_director_count=2,
            total_value=150_000.0,
            has_c_level=True,
            is_opportunistic=True,
            is_cluster=True,
        )
    ]

    horizons = [("21d", 21, "1 Ay (21 İş Günü)")]
    results = run_sec_form4_event_study(
        events,
        benchmark_symbol="SPY",
        history=_mock_history,
        horizons=horizons,
        estimated_slippage_pct=0.5,
    )

    assert results["evaluated_events"] == 1
    h21 = results["horizons"]["21d"]
    assert h21["avg_stock_return_pct"] == pytest.approx(15.0)
    assert h21["avg_benchmark_return_pct"] == pytest.approx(5.0)
    assert h21["avg_excess_return_pct"] == pytest.approx(10.0)
    assert h21["net_excess_return_pct"] == pytest.approx(9.5)  # 10.0 - 0.5% slippage

    report = format_sec_form4_study_report(results)
    assert "Alfa: +%10.00" in report
    assert "Net: %+9.50" in report
    assert "VERİYE DAYALI BULGULAR VE ANALİZ:" in report
    # Sample size is 1 (< 30), so a sample size warning must be rendered!
    assert "Örneklem uyarısı" in report


def test_parse_sec_atom_feed() -> None:
    xml_sample = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
            <title>4 - WEYCO GROUP INC (0000106532) (Issuer)</title>
            <link href="https://www.sec.gov/Archives/edgar/data/106532/000119494826000017/index.htm"/>
            <updated>2026-11-10T17:30:00-05:00</updated>
            <summary type="html">Filing Form 4</summary>
        </entry>
        <entry>
            <title>4 - FLORSHEIM THOMAS W JR (0001194948) (Reporting)</title>
            <link href="https://www.sec.gov/Archives/edgar/data/1194948/000119494826000017/index.htm"/>
            <updated>2026-11-10T17:30:00-05:00</updated>
            <summary type="html">Reporting Owner</summary>
        </entry>
    </feed>
    """
    entries = parse_sec_atom_feed(xml_sample)
    assert len(entries) == 2
    assert entries[0]["entity_name"] == "WEYCO GROUP INC"
    assert entries[0]["cik"] == "0000106532"
    assert entries[0]["entity_role"] == "Issuer"
    assert "Archives/edgar" in entries[0]["link"]
