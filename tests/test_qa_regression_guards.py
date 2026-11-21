# -*- coding: utf-8 -*-
"""Regression guards for QA Audit Phase 1-3 fixes (BUG-01..BUG-11 & Alpha v2)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.config import get_litellm_model_providers
from src.mcp.tools import _handle_strategic_trading_brief
from src.quant.ai_council import _trim_text
from src.quant.data_loader import load_universe_closes
from src.quant.portfolio import save_champion_paper_snapshot
from src.quant.stats import classify_strategy_verdict, compute_performance_metrics
from src.quant.strategies.engine import StrategyResult
from src.quant.strategies.library import compute_meta_a_weights, compute_paa_weights
from src.services.bist_screener import is_non_equity_kap_issuer


def _synthetic_prices(
    symbols: list[str],
    start: str = "2018-01-02",
    periods: int = 1600,
    drift: float = 0.0003,
) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    rng = np.random.default_rng(42)
    data = {}
    for idx, sym in enumerate(symbols):
        rets = rng.normal(drift + idx * 0.00001, 0.008, size=periods)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


def test_load_universe_closes_never_poisons_wider_cache(tmp_path: Path) -> None:
    """BUG-01: Narrower/later load_universe_closes calls must never truncate or overwrite a wider CSV cache."""
    wide_syms = [f"ETF{i}" for i in range(25)]
    wide_df = _synthetic_prices(wide_syms, start="2018-01-02", periods=1800)
    cache_file = tmp_path / "closes_us_etf_and_sectors.csv"
    wide_df.to_csv(cache_file)

    narrow_syms = wide_syms[:12]
    with patch("yfinance.download") as mock_dl:
        result = load_universe_closes(
            "us_etf_and_sectors",
            narrow_syms,
            start_date="2023-01-01",
            cache_dir=tmp_path,
            force_refresh=False,
        )
        # Should satisfy from existing wider cache without downloading or overwriting
        mock_dl.assert_not_called()

    assert list(result.columns) == narrow_syms
    assert result.index.min() >= pd.Timestamp("2023-01-01")

    # On-disk cache MUST remain untouched with full 2018 history and all 25 columns
    persisted = pd.read_csv(cache_file, index_col=0, parse_dates=True)
    assert len(persisted.columns) == 25
    assert persisted.index.min() <= pd.Timestamp("2018-01-05")

    # Even when force_refresh=True with narrower symbols, non-destructive merge preserves existing columns
    narrow_fresh = _synthetic_prices(narrow_syms, start="2023-01-02", periods=400)
    raw_yf = pd.concat({"Close": narrow_fresh}, axis=1)
    with patch("yfinance.download", return_value=raw_yf):
        load_universe_closes(
            "us_etf_and_sectors",
            narrow_syms,
            start_date="2023-01-01",
            cache_dir=tmp_path,
            force_refresh=True,
        )
    merged = pd.read_csv(cache_file, index_col=0, parse_dates=True)
    assert len(merged.columns) == 25
    assert merged.index.min() <= pd.Timestamp("2018-01-05")


def test_get_litellm_model_providers_concurrent_threads_no_deadlock() -> None:
    """BUG-02: Concurrent calls to get_litellm_model_providers must never deadlock or raise circular import errors."""
    errors: list[Exception] = []
    results: list[set[str]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def _worker() -> None:
        try:
            barrier.wait(timeout=5.0)
            providers = get_litellm_model_providers()
            with lock:
                results.append(set(providers))
        except Exception as exc:  # pragma: no cover - regression failure path
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20.0)

    assert not errors, f"Concurrent litellm provider resolution failed: {errors}"
    assert len(results) == 8
    assert all(len(r) > 0 for r in results)


def test_excess_sharpe_verdict_rejects_sub_rf_and_short_oos_window() -> None:
    """BUG-03: Sub-BIL strategies and short OOS windows must never receive PASS_SOLID/PASS_ELITE."""
    dates = pd.bdate_range("2022-01-03", periods=1001)
    rf_daily = pd.Series((1.045 ** (1.0 / 252.0)) - 1.0, index=dates)

    # 1) Strategy earning ~3.0%/yr when BIL earns +4.5%/yr -> negative excess return -> FAIL_WEAK
    rng = np.random.default_rng(7)
    sub_rf_rets = pd.Series(
        ((1.030 ** (1.0 / 252.0)) - 1.0) + rng.normal(0.0, 0.002, size=len(dates)),
        index=dates,
    )
    sub_rf_eq = 100.0 * (1.0 + sub_rf_rets).cumprod()
    sub_metrics = compute_performance_metrics(sub_rf_eq, rf_returns=rf_daily)
    assert sub_metrics.excess_cagr_pct < 0.0
    assert sub_metrics.excess_sharpe < 0.0
    verdict = classify_strategy_verdict(sub_metrics, universe="us_etf", min_oos_days=750)
    assert verdict == "FAIL_WEAK"

    # 2) Strong strategy (+14%/yr) with only 472 OOS trading days when min_oos_days=750 -> FAIL_WEAK
    short_dates = dates[:473]
    strong_short_rets = pd.Series(
        ((1.14 ** (1.0 / 252.0)) - 1.0) + rng.normal(0.0, 0.005, size=len(short_dates)),
        index=short_dates,
    )
    strong_short_eq = 100.0 * (1.0 + strong_short_rets).cumprod()
    short_metrics = compute_performance_metrics(strong_short_eq, rf_returns=rf_daily.iloc[:473])
    assert short_metrics.excess_sharpe > 0.5
    assert short_metrics.trading_days == 472
    verdict_short = classify_strategy_verdict(short_metrics, universe="us_etf", min_oos_days=750)
    assert verdict_short == "FAIL_WEAK"

    # 3) Genuine elite strategy (+14%/yr, low vol, 1000 days) -> PASS_ELITE
    strong_full_rets = pd.Series(
        ((1.14 ** (1.0 / 252.0)) - 1.0) + rng.normal(0.0, 0.005, size=len(dates)),
        index=dates,
    )
    strong_full_eq = 100.0 * (1.0 + strong_full_rets).cumprod()
    elite_metrics = compute_performance_metrics(strong_full_eq, rf_returns=rf_daily)
    verdict_elite = classify_strategy_verdict(elite_metrics, universe="us_etf", min_oos_days=750)
    assert verdict_elite == "PASS_ELITE"


def test_bist_non_equity_kap_filter() -> None:
    """BUG-04: Exclude KAP bond/sukuk/leasing/factoring SPVs while retaining traded BIST equities."""
    excluded_spvs = [
        ("AKTVK.IS", "AKTİF BANK SUKUK VARLIK KİRALAMA A.Ş."),
        ("HALKF.IS", "HALK FİNANSAL KİRALAMA A.Ş."),
        ("KOCFN.IS", "KOÇ FİNANSMAN A.Ş."),
        ("KLVKS.IS", "KALKINMA YATIRIM VARLIK KİRALAMA A.Ş."),
        ("GARFL.IS", "GARANTİ FAKTORİNG A.Ş."),
        ("QNBFF.IS", "QNB FİNANSAL KİRALAMA A.Ş."),
        ("DENFA.IS", "DENİZ FAKTORİNG A.Ş."),
    ]
    for code, name in excluded_spvs:
        assert is_non_equity_kap_issuer(code, name) is True, f"Expected SPV/non-equity {code} to be filtered"

    kept_equities = [
        ("THYAO.IS", "TÜRK HAVA YOLLARI A.O."),
        ("GARAN.IS", "TÜRKİYE GARANTİ BANKASI A.Ş."),
        ("AKBNK.IS", "AKBANK T.A.Ş."),
        ("ASELS.IS", "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş."),
        ("A1CAP.IS", "A1 CAPİTAL YATIRIM MENKUL DEĞERLER A.Ş."),
        ("ALBRK.IS", "ALBARAKA TÜRK KATILIM BANKASI A.Ş."),
        ("ISMEN.IS", "İŞ YATIRIM MENKUL DEĞERLER A.Ş."),
    ]
    for code, name in kept_equities:
        assert is_non_equity_kap_issuer(code, name) is False, f"Expected traded equity {code} to be kept"


def test_mcp_strategic_trading_brief_compact_payload_under_15kb() -> None:
    """BUG-06: Default compact=True strategic trading brief stays well below 15 KB."""
    fake_tournament = {
        "generated_at": "2026-11-21T10:00:00Z",
        "oos_start": "2022-01-01",
        "strategy_count": 25,
        "verdict_counts": {"PASS_ELITE": 3, "PASS_SOLID": 5, "FAIL_WEAK": 17},
        "champion": {
            "strategy_id": "META_US_ETF_ALL_WEATHER",
            "name": "Meta-Portföy A v2",
            "verdict": "PASS_ELITE",
            "oos_metrics": {"cagr_pct": 10.9, "sharpe": 1.13, "excess_sharpe": 0.75, "max_drawdown_pct": -8.3},
            "equity_curve": [{"date": f"2022-01-{i:02d}", "nav": 100.0 + i} for i in range(1, 200)],
        },
        "leaderboard": [
            {
                "strategy_id": f"STRAT_{idx}",
                "name": f"Strategy {idx}",
                "universe": "us_etf",
                "verdict": "PASS_ELITE",
                "oos_metrics": {"cagr_pct": 10.0, "sharpe": 1.0, "excess_sharpe": 0.6, "max_drawdown_pct": -10.0},
                "equity_curve": [{"date": "2022-01-01", "nav": 100.0}] * 250,
            }
            for idx in range(10)
        ],
    }
    fake_books = {
        "books": {
            "meta_a": {
                "strategy": "meta_a",
                "nav": 10500.0,
                "total_return_pct": 5.0,
                "as_of_date": "2026-11-20",
                "target_weights": {"BIL": 0.8, "SHY": 0.2},
                "nav_history": [{"date": "2026-01-01", "nav": 10000.0}] * 500,
                "trades": [{"symbol": "SPY", "side": "BUY"}] * 300,
            }
        }
    }

    with (
        patch("src.quant.tournament.load_latest_tournament_results", return_value=fake_tournament),
        patch("src.quant.tournament.get_live_paa_signal", return_value={"ok": True, "regime_label": "DEFENSIVE", "target_weights_pct": {"BIL": 100.0}}),
        patch("src.quant.paper_book.get_quant_paper_books_status", return_value=fake_books),
        patch("src.mcp.tools._handle_market_regime", return_value={"ok": True, "data": {"regime": "risk_off", "position_scale": 0.0}}),
        patch("src.mcp.tools._handle_paper_portfolio", return_value={"ok": True, "data": {"open_position_count": 0, "trades": []}}),
        patch("src.mcp.tools._handle_decision_signals", return_value={"ok": True, "data": {"items": []}}),
        patch("src.mcp.tools._handle_crypto_trend_signal", return_value={"ok": True, "data": {"signals": {}}}),
        patch("src.services.kap_watch_service.get_recent_kap_and_news_alerts", return_value=[]),
    ):
        resp = _handle_strategic_trading_brief({"compact": True})

    raw = json.dumps(resp, ensure_ascii=False).encode("utf-8")
    assert resp["ok"] is True
    assert len(raw) < 15_000, f"Compact strategic brief too large: {len(raw)} bytes"
    assert "equity_curve" not in raw.decode("utf-8")
    assert "nav_history" not in raw.decode("utf-8")


def test_champion_paper_snapshot_includes_date_and_nav(tmp_path: Path) -> None:
    """BUG-11: Quant champion snapshot includes standard date and nav keys."""
    eq = 100.0 * (1.0 + pd.Series([0.0005] * 260, index=pd.bdate_range("2025-01-02", periods=260))).cumprod()
    dummy_metrics = compute_performance_metrics(eq)
    champ = StrategyResult(
        strategy_id="META_US_ETF_ALL_WEATHER",
        name="Meta-Portföy A v2",
        universe="us_etf",
        category="meta",
        description="Meta-Portfolio A v2 test fixture",
        currency="USD",
        cost_bps=5.0,
        is_benchmark=False,
        verdict="PASS_ELITE",
        oos=dummy_metrics,
        full=dummy_metrics,
        current_weights={"BIL": 80.0, "SHY": 20.0},
        cash_weight_pct=0.0,
        latest_date="2026-11-20",
    )
    out_file = tmp_path / "quant_champion_paper.json"
    state = save_champion_paper_snapshot(champ, initial_capital=10_000.0, path=out_file)
    assert state["latest"]["date"] == "2026-11-20"
    assert state["latest"]["as_of_date"] == "2026-11-20"
    assert state["latest"]["nav"] == 10_000.0
    assert out_file.is_file()


def test_ai_council_trim_text_respects_word_boundary_and_budget() -> None:
    """BUG-09: AI Council thesis/rationale trimming avoids mid-word truncation."""
    long_text = " ".join(f"word{i}" for i in range(400))
    trimmed = _trim_text(long_text, 1200)
    assert len(trimmed) <= 1203
    assert trimmed.endswith("...")
    # Ensure the token immediately before '...' is a complete word from the source
    last_token = trimmed[:-3].split()[-1]
    assert last_token in long_text.split()


def test_alpha_v2_paa_and_meta_a_use_bil_safe_haven() -> None:
    """Phase 2 Alpha v2: PAA v2 and Meta-Portfolio A v2 rotate into BIL during broad market drawdowns."""
    dates = pd.bdate_range("2020-01-02", periods=600)
    data = {}
    # All risky ETFs falling steadily -> below 12M SMA -> full crash protection
    for sym in ("SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD", "TLT", "IEF", "LQD", "HYG"):
        data[sym] = np.linspace(150.0, 70.0, len(dates))
    # BIL rising steadily -> best cash-equivalent safe haven
    data["BIL"] = np.linspace(90.0, 96.0, len(dates))
    data["SHY"] = np.linspace(84.0, 82.0, len(dates))
    prices = pd.DataFrame(data, index=dates)

    paa_w = compute_paa_weights(prices)
    last_paa = paa_w.iloc[-1]
    assert float(last_paa.get("BIL", 0.0)) >= 0.95

    meta_w = compute_meta_a_weights(prices)
    last_meta = meta_w.iloc[-1]
    assert float(last_meta.get("BIL", 0.0)) >= 0.60
