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
    SecForm4Fetcher,
    cluster_insider_transactions,
    parse_sec_atom_feed,
)
from src.services.sec_form4_screener import (
    format_sec_screener_report,
    score_insider_event,
    screen_us_insider_stocks,
)
from src.services.sec_form4_study import (
    format_sec_form4_study_report,
    run_sec_form4_event_study,
)


def _make_mock_zip() -> bytes:
    """Create a minimal in-memory SEC Form 3/4/5 zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # SUBMISSION.tsv
        sub_content = (
            "ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\tISSUERNAME\tISSUERTRADINGSYMBOL\tAFF10B5ONE\n"
            "001-01\t02-MAR-2026\t01-MAR-2026\t4\tAcme Corp\tACME\t0\n"
            "001-02\t03-MAR-2026\t02-MAR-2026\t4\tAcme Corp\tACME\t0\n"
            "002-01\t05-MAR-2026\t04-MAR-2026\t4\tBeta Inc\tBETA\t1\n"
        )
        z.writestr("SUBMISSION.tsv", sub_content)

        # REPORTINGOWNER.tsv
        owner_content = (
            "ACCESSION_NUMBER\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
            "001-01\tJohn Doe\tOfficer\tChief Executive Officer\n"
            "001-02\tJane Smith\tOfficer\tChief Financial Officer\n"
            "002-01\tBob Routine\tDirector\tDirector\n"
        )
        z.writestr("REPORTINGOWNER.tsv", owner_content)

        # NONDERIV_TRANS.tsv
        trans_content = (
            "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tSECURITY_TITLE\n"
            "001-01\t01-MAR-2026\tP\t1000.0\t100.0\tCommon Stock\n"  # ACME CEO: $100k
            "001-02\t02-MAR-2026\tP\t500.0\t100.0\tCommon Stock\n"   # ACME CFO: $50k
            "001-02\t02-MAR-2026\tS\t200.0\t100.0\tCommon Stock\n"   # Sale -> ignored
            "002-01\t04-MAR-2026\tP\t500.0\t50.0\tCommon Stock\n"    # BETA Director 10b5-1: $25k
        )
        z.writestr("NONDERIV_TRANS.tsv", trans_content)
    return buf.getvalue()


def test_parse_quarter_tsv_and_clustering(tmp_path) -> None:
    zip_bytes = _make_mock_zip()
    mock_zip_file = tmp_path / "mock_2026q1.zip"
    mock_zip_file.write_bytes(zip_bytes)

    fetcher = SecForm4Fetcher(cache_dir=tmp_path)
    events = fetcher.parse_quarter("2026q1", zip_path=mock_zip_file, min_value=10_000.0)

    # ACME has 2 purchases by 2 distinct officers (CEO and CFO) within 2 days -> clustered!
    # BETA has 1 purchase by Director -> single
    assert len(events) == 2
    acme_event = next(e for e in events if e.symbol == "ACME")
    assert acme_event.insider_count == 2
    assert acme_event.is_cluster is True
    assert acme_event.has_c_level is True
    assert acme_event.is_opportunistic is True
    assert acme_event.total_value == 150_000.0

    beta_event = next(e for e in events if e.symbol == "BETA")
    assert beta_event.insider_count == 1
    assert beta_event.is_cluster is False
    assert beta_event.is_opportunistic is False  # 10b5-1 is True
    assert beta_event.total_value == 25_000.0


def test_scoring_and_screening() -> None:
    e_cluster = InsiderClusterEvent(
        symbol="ACME",
        company_name="Acme Corp",
        filing_date=date(2026, 3, 2),
        insider_count=2,
        total_value=150_000.0,
        total_shares=1500.0,
        avg_price=100.0,
        has_c_level=True,
        is_opportunistic=True,
        is_cluster=True,
        primary_titles=["Chief Executive Officer", "Chief Financial Officer"],
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
        total_value=25_000.0,
        total_shares=500.0,
        avg_price=50.0,
        has_c_level=False,
        is_opportunistic=False,
        is_cluster=False,
        primary_titles=["Director"],
    )
    score_rot, _ = score_insider_event(e_routine)
    assert score_rot < 40  # 10 (single) + 0 - 10 (10b5-1) + 5 = 5

    candidates = screen_us_insider_stocks([e_routine, e_cluster], min_score=40, top_n=5)
    assert len(candidates) == 1
    assert candidates[0].symbol == "ACME"
    assert candidates[0].score == score

    text = format_sec_screener_report(candidates)
    assert "ACME (Acme Corp)" in text
    assert "python main.py --stocks ACME" in text


def test_sec_form4_event_study_prevents_lookahead_and_computes_alpha() -> None:
    from datetime import timedelta

    # Mock calendar with 30 daily bars
    # Event filing_date: 2026-03-02
    # Next trading day entry: 2026-03-03
    t0 = date(2026, 3, 2)
    fake_acme_closes = {}
    fake_spy_closes = {}

    # ACME starts at 100 on 2026-03-03, rises +15% over 21 trading days
    # SPY starts at 500 on 2026-03-03, rises +5% over 21 trading days
    cur_d = t0
    acme_px = 98.0
    spy_px = 495.0
    for day_idx in range(40):
        cur_d = t0 + timedelta(days=day_idx)
        if day_idx == 1:  # 2026-03-03 (entry date)
            acme_px = 100.0
            spy_px = 500.0
        elif day_idx == 22:  # 21 trading days after entry
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
    )

    assert results["evaluated_events"] == 1
    h21 = results["horizons"]["21d"]
    assert h21["avg_stock_return_pct"] == pytest.approx(15.0)
    assert h21["avg_benchmark_return_pct"] == pytest.approx(5.0)
    assert h21["avg_excess_return_pct"] == pytest.approx(10.0)
    assert h21["win_rate_pct"] == 100.0

    report = format_sec_form4_study_report(results)
    assert "Alfa: +%10.00" in report
    assert "Küme Alımı" in report


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
