# -*- coding: utf-8 -*-
"""Tests for the Borsa Istanbul autocomplete seed and index merge."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_kap_stock_list as kap_seed  # noqa: E402
import generate_index_from_csv as gen  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("TÜRK HAVA YOLLARI A.O.", "Türk Hava Yolları A.O."),
        ("TÜRKİYE İŞ BANKASI A.Ş.", "Türkiye İş Bankası A.Ş."),
        ("EREĞLİ DEMİR VE ÇELİK FABRİKALARI T.A.Ş.", "Ereğli Demir ve Çelik Fabrikaları T.A.Ş."),
        ("TÜPRAŞ-TÜRKİYE PETROL RAFİNERİLERİ A.Ş.", "Tüpraş-Türkiye Petrol Rafinerileri A.Ş."),
        ("İHLAS HOLDİNG A.Ş.", "İhlas Holding A.Ş."),
    ],
)
def test_turkish_title_case(raw: str, expected: str) -> None:
    assert kap_seed.turkish_title(raw) == expected


def test_seed_rows_have_suffix_codes_and_ascii_aliases() -> None:
    rows = kap_seed.build_seed_rows({
        "THYAO": {"mkk_member_oid": "x", "title": "TÜRK HAVA YOLLARI A.O."},
        "ISCTR": {"mkk_member_oid": "y", "title": "TÜRKİYE İŞ BANKASI A.Ş."},
        "bad-code": {"mkk_member_oid": "z", "title": "IGNORED A.Ş."},
        "NONAME": {"mkk_member_oid": "w", "title": ""},
    })
    by_code = {row["ts_code"]: row for row in rows}
    assert set(by_code) == {"THYAO.IS", "ISCTR.IS"}
    thy = by_code["THYAO.IS"]
    assert thy["symbol"] == "THYAO.IS"
    assert thy["name"] == "Türk Hava Yolları A.O."
    assert thy["aliases"].split("|") == ["THYAO", "Türk Hava Yolları", "Turk Hava Yollari", "TÜRK HAVA YOLLARI A.O."]
    assert "Turkiye Is Bankasi" in by_code["ISCTR.IS"]["aliases"]


def test_generator_maps_is_suffix_to_tr_and_keeps_suffix() -> None:
    assert gen.determine_market("THYAO.IS") == "TR"
    assert gen.extract_symbol_from_ts_code("THYAO.IS", "TR") == "THYAO.IS"
    parsed = gen.parse_stock_row(
        {"ts_code": "THYAO.IS", "symbol": "THYAO.IS", "name": "Türk Hava Yolları A.O.", "aliases": "THYAO|Turk Hava Yollari"},
        "TR",
    )
    assert parsed["market"] == "TR"
    assert parsed["aliases"] == ["THYAO", "Turk Hava Yollari"]


def test_merge_replaces_only_selected_markets() -> None:
    existing = [
        ["600519.SH", "600519", "贵州茅台", "", "", [], "CN", "stock", True, 100],
        ["OLD.IS", "OLD.IS", "Old", "", "", [], "TR", "stock", True, 100],
        ["7203.T", "7203.T", "丰田汽车", "", "", [], "JP", "stock", True, 100],
    ]
    replacement = [["THYAO.IS", "THYAO.IS", "Türk Hava Yolları A.O.", "", "", [], "TR", "stock", True, 100]]
    merged = gen.merge_compressed_index(existing, replacement, ["TR"])
    assert [row[0] for row in merged] == ["600519.SH", "7203.T", "THYAO.IS"]


def test_committed_seed_and_index_contain_bist_entries() -> None:
    seed = (REPO_ROOT / "scripts" / "stock_index_seeds" / "stock_list_tr.csv").read_text(encoding="utf-8")
    assert seed.splitlines()[0] == "ts_code,symbol,name,enname,aliases"
    assert "THYAO.IS,THYAO.IS,Türk Hava Yolları A.O." in seed
    index = json.loads((REPO_ROOT / "apps" / "dsa-web" / "public" / "stocks.index.json").read_text(encoding="utf-8"))
    tr_rows = [row for row in index if row[6] == "TR"]
    assert len(tr_rows) > 500
    assert all(row[0].endswith(".IS") and row[1] == row[0] for row in tr_rows)
    assert len({row[0] for row in index}) == len(index)


def test_backend_index_resolves_bist_name_and_keeps_bare_ticker_strict() -> None:
    from src.data.stock_index_loader import get_index_stock_name, resolve_index_stock_code_candidates

    assert get_index_stock_name("THYAO.IS") == "Türk Hava Yolları A.O."
    # Bare BIST tickers are not silently rewritten to .IS (they collide with US tickers).
    assert "THYAO.IS" not in resolve_index_stock_code_candidates("THYAO")
