# -*- coding: utf-8 -*-
"""Offline unit & API tests for QuantStats-style visual tearsheet."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from api.app import create_app
from src.quant.tearsheet import (
    build_quant_tearsheet,
    build_underwater_series,
    compute_monthly_returns_matrix,
)


def test_monthly_matrix_and_underwater_math() -> None:
    dates = pd.date_range("2025-01-01", "2025-04-30", freq="B")
    vals = 100.0 * np.cumprod(np.where((np.arange(len(dates)) % 15) == 0, 0.96, 1.005))
    eq = pd.Series(vals, index=dates)

    rows, stats = compute_monthly_returns_matrix(eq)
    assert len(rows) == 1
    assert rows[0]["year"] == 2025
    assert {"1", "2", "3", "4"} <= set(rows[0]["months"].keys())
    assert stats["months_count"] == 4
    assert stats["best_month_pct"] >= stats["worst_month_pct"]

    uw = build_underwater_series(eq, eq * 0.9)
    assert len(uw) == len(eq)
    assert uw[0]["drawdown_pct"] == pytest.approx(0.0)
    assert min(pt["drawdown_pct"] for pt in uw) < 0.0


def test_tearsheet_paper_mode_and_endpoint(tmp_path: Path) -> None:
    book = {
        "name": "quant_meta_a",
        "label": "Meta-A Demo",
        "history": [
            {"date": "2026-10-30", "nav": 10000.0, "benchmark_nav": 10000.0},
            {"date": "2026-11-02", "nav": 10100.0, "benchmark_nav": 9900.0},
            {"date": "2026-11-20", "nav": 10201.0, "benchmark_nav": 9700.0},
        ],
    }
    (tmp_path / "quant_meta_a.json").write_text(json.dumps(book), encoding="utf-8")

    ts = build_quant_tearsheet(
        "meta_a",
        mode="paper",
        book_dir=tmp_path,
        macro_snapshot={"usd_try": 50.0, "usd_try_1y_change_pct": 25.0, "cpi_yoy_pct": 35.0, "cpi_source": "tcmb_evds2"},
    )
    assert ts["ok"] is True
    assert ts["monthly_matrix"][0]["year"] == 2026
    assert ts["metrics"]["total_return_pct"] == pytest.approx(2.01)
    assert ts["currency_comparison"]["real_tufe_1y_return_pct"] is not None

    app = create_app()
    client = TestClient(app)
    res = client.get("/api/v1/alpha/tearsheet?strategy=v3_trp&mode=backtest")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["strategy_key"] == "v3_trp"
    assert len(body["underwater"]) >= 50
    assert len(body["monthly_matrix"]) >= 8
