# -*- coding: utf-8 -*-
"""3-AI Quantitative Strategy Council (Claude CLI · Codex CLI · Gemini CLI).

Convenes local Claude Code CLI, OpenAI Codex CLI, and Google Gemini CLI with
today's verified market regime, PAA breadth, and 25-strategy OOS tournament data.
Each CLI authors a structured, deterministic, zero-lookahead strategy charter
validated via OOS backtest (2022+) and tracked daily from creation date inside
``QuantAllocationPaperBook`` (strictly simulated; never real broker orders).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.agent.cli_bridge_common import (
    build_cli_subprocess_env,
    resolve_cli_binary,
    terminate_process_tree,
)
from src.quant.data_loader import (
    US_ETF_UNIVERSE,
    US_SECTOR_FACTOR_UNIVERSE,
    load_universe_closes,
)
from src.quant.stats import classify_strategy_verdict
from src.quant.strategies.engine import (
    DEFAULT_OOS_START,
    StrategySpec,
    backtest_weight_matrix,
)
from src.quant.strategies.library import _causal_rebalance, compute_paa_weights
from src.services.strategy_paper_book import (
    DEFAULT_BOOK_DIR,
    QuantAllocationPaperBook,
    format_quant_book_report,
)

logger = logging.getLogger(__name__)

COUNCIL_CHARTERS_FILENAME = "ai_council_charters.json"
ALLOWED_COUNCIL_ETFS: tuple[str, ...] = tuple(
    dict.fromkeys([*US_ETF_UNIVERSE, *US_SECTOR_FACTOR_UNIVERSE])
)
DEFAULT_SAFE_ASSETS: tuple[str, ...] = ("SHY", "IEF", "BIL")

ALLOWED_RULE_ENGINES = frozenset(
    {
        "paa_custom",
        "vol_target_trend",
        "safe_haven_momentum",
        "dual_sma_trend",
        "all_weather_trend_parity",
        "barbell_defensive",
    }
)

COUNCIL_MEMBER_META: Dict[str, Dict[str, str]] = {
    "claude": {
        "member_key": "claude",
        "strategy_key": "council_claude",
        "book_name": "council_claude",
        "engine_label": "Claude Code CLI",
        "binary": "claude",
        "path_env": "DSA_CLAUDE_CLI_PATH",
        "model_env": "DSA_CLAUDE_CLI_MODEL",
    },
    "codex": {
        "member_key": "codex",
        "strategy_key": "council_codex",
        "book_name": "council_codex",
        "engine_label": "OpenAI Codex CLI",
        "binary": "codex",
        "path_env": "DSA_CODEX_CLI_PATH",
        "model_env": "DSA_CODEX_CLI_MODEL",
    },
    "gemini": {
        "member_key": "gemini",
        "strategy_key": "council_gemini",
        "book_name": "council_gemini",
        "engine_label": "Google Gemini CLI",
        "binary": "gemini",
        "path_env": "DSA_GEMINI_CLI_PATH",
        "model_env": "DSA_GEMINI_CLI_MODEL",
    },
}


# ---------------------------------------------------------------------------
# Price loading (combined 30-ETF universe)
# ---------------------------------------------------------------------------


def load_council_etf_prices(
    *,
    start_date: str = "2018-01-01",
    force_refresh: bool = False,
    cache_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Load completed daily closes for the 30-ETF council universe (US ETF + Sectors/Factors)."""
    us_etf = load_universe_closes(
        "us_etf",
        US_ETF_UNIVERSE,
        start_date=start_date,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    us_sec = load_universe_closes(
        "us_sectors",
        US_SECTOR_FACTOR_UNIVERSE,
        start_date=start_date,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    frames = [df for df in (us_etf, us_sec) if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, axis=1)
    combined = combined.loc[:, ~combined.columns.duplicated()].sort_index().ffill()
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    completed = combined[combined.index < today]
    return completed if not completed.empty else combined


# ---------------------------------------------------------------------------
# Deterministic, zero-lookahead parameterized rule compilers (zero eval)
# ---------------------------------------------------------------------------


def _filter_symbols(
    raw: Any,
    prices: pd.DataFrame,
    fallback: Sequence[str],
    *,
    min_count: int = 1,
) -> List[str]:
    allowed = set(ALLOWED_COUNCIL_ETFS) & set(prices.columns)
    cleaned: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            sym = str(item or "").strip().upper()
            if sym in allowed and sym not in cleaned:
                cleaned.append(sym)
    if len(cleaned) < min_count:
        for fb in fallback:
            if fb in allowed and fb not in cleaned:
                cleaned.append(fb)
    return cleaned


def _pick_safe(raw: Any, prices: pd.DataFrame, fallback: str = "SHY") -> str:
    allowed = set(ALLOWED_COUNCIL_ETFS) & set(prices.columns)
    cand = str(raw or "").strip().upper()
    if cand in allowed:
        return cand
    for fb in (fallback, "SHY", "BIL", "IEF"):
        if fb in allowed:
            return fb
    return next(iter(sorted(allowed)), "SHY")


def _clamp_int(val: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(val)))))
    except (TypeError, ValueError):
        return default


def _clamp_float(val: Any, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return default


def compile_council_weight_fn(charter: Dict[str, Any]) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Compile a validated AI Strategy Charter into a deterministic zero-lookahead weight builder."""
    engine = str(charter.get("rule_engine") or "vol_target_trend").strip().lower()
    if engine not in ALLOWED_RULE_ENGINES:
        engine = "vol_target_trend"
    params = charter.get("params") if isinstance(charter.get("params"), dict) else {}
    freq = "W" if str(params.get("rebalance_freq") or "M").strip().upper().startswith("W") else "M"

    def _build(prices: pd.DataFrame) -> pd.DataFrame:
        if prices is None or prices.empty:
            return pd.DataFrame()

        if engine == "paa_custom":
            risk_assets = _filter_symbols(
                params.get("risk_assets"),
                prices,
                ("SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT"),
                min_count=4,
            )
            safe_assets = _filter_symbols(params.get("safe_assets"), prices, ("SHY", "IEF"), min_count=1)
            lookback = _clamp_int(params.get("lookback_days"), 210, 63, 260)
            top_n = _clamp_int(params.get("top_n"), 4, 1, 8)
            pf = _clamp_float(params.get("protection_factor"), 2.0, 1.0, 3.0)
            return compute_paa_weights(
                prices,
                risk_assets=risk_assets,
                safe_assets=safe_assets,
                lookback_days=lookback,
                top_n=top_n,
                protection_factor=pf,
            )

        if engine == "vol_target_trend":
            risky = _filter_symbols(
                params.get("risk_assets") or params.get("assets"),
                prices,
                ("SPY", "QQQ", "GLD", "TLT", "DBC", "XLV", "XLE"),
                min_count=2,
            )
            safe = _pick_safe(params.get("safe_asset"), prices, "SHY")
            cols = list(dict.fromkeys([*risky, safe]))
            sma_win = _clamp_int(params.get("sma_window"), 150, 50, 252)
            vol_win = _clamp_int(params.get("vol_window"), 42, 20, 90)
            target_vol = _clamp_float(params.get("target_vol_pct"), 10.0, 4.0, 20.0) / 100.0
            max_w = _clamp_float(params.get("max_weight"), 0.35, 0.15, 0.60)

            sma = prices[risky].rolling(sma_win, min_periods=min(sma_win, 50)).mean()
            ann_vol = prices[risky].pct_change().rolling(vol_win, min_periods=min(vol_win, 20)).std() * np.sqrt(252.0)
            w = pd.DataFrame(0.0, index=prices.index, columns=cols)
            per_sleeve_vol = target_vol / max(1, len(risky))
            for c in risky:
                raw_w = (per_sleeve_vol / ann_vol[c].replace(0.0, np.nan)).clip(upper=max_w).fillna(0.0)
                w[c] = np.where(prices[c] > sma[c], raw_w, 0.0)
            total = w[risky].sum(axis=1)
            over = total > 1.0
            if bool(over.any()):
                w.loc[over, risky] = w.loc[over, risky].div(total[over], axis=0)
            w[safe] = (1.0 - w[risky].sum(axis=1)).clip(lower=0.0)
            return _causal_rebalance(w, freq)

        if engine == "safe_haven_momentum":
            offensive = _filter_symbols(
                params.get("offensive_assets") or params.get("assets"),
                prices,
                ("GLD", "DBC", "TLT", "IEF", "XLE", "XLV", "USMV"),
                min_count=2,
            )
            defensive = _filter_symbols(params.get("defensive_assets"), prices, ("SHY", "BIL", "IEF"), min_count=1)
            cols = list(dict.fromkeys([*offensive, *defensive]))
            mom_days = _clamp_int(params.get("momentum_days"), 126, 21, 252)
            sma_days = _clamp_int(params.get("sma_filter_days"), 150, 50, 252)
            top_n = _clamp_int(params.get("top_n"), 2, 1, 5)

            mom = prices[cols].pct_change(mom_days)
            sma = prices[cols].rolling(sma_days, min_periods=min(sma_days, 50)).mean()
            w = pd.DataFrame(0.0, index=prices.index, columns=cols)
            warmup = max(mom_days, sma_days)
            for idx in range(min(warmup, len(prices)), len(prices)):
                elig = [
                    (c, float(mom[c].iloc[idx]))
                    for c in offensive
                    if pd.notna(mom[c].iloc[idx])
                    and pd.notna(sma[c].iloc[idx])
                    and float(mom[c].iloc[idx]) > 0.0
                    and float(prices[c].iloc[idx]) > float(sma[c].iloc[idx])
                ]
                elig.sort(key=lambda kv: kv[1], reverse=True)
                chosen = elig[:top_n]
                if chosen:
                    each = 1.0 / len(chosen)
                    for sym, _ in chosen:
                        w.iat[idx, cols.index(sym)] = each
                else:
                    def_vals = [(c, float(mom[c].iloc[idx])) for c in defensive if pd.notna(mom[c].iloc[idx])]
                    best_def = max(def_vals, key=lambda kv: kv[1])[0] if def_vals else defensive[0]
                    w.iat[idx, cols.index(best_def)] = 1.0
            return _causal_rebalance(w, freq)

        if engine == "dual_sma_trend":
            assets = _filter_symbols(
                params.get("assets") or params.get("risk_assets"),
                prices,
                ("SPY", "QQQ", "GLD", "DBC", "XLV", "USMV"),
                min_count=2,
            )
            safe = _pick_safe(params.get("safe_asset"), prices, "SHY")
            cols = list(dict.fromkeys([*assets, safe]))
            fast = _clamp_int(params.get("fast_sma"), 50, 15, 120)
            slow = _clamp_int(params.get("slow_sma"), 200, max(fast + 20, 80), 252)

            sma_f = prices[assets].rolling(fast, min_periods=min(fast, 20)).mean()
            sma_s = prices[assets].rolling(slow, min_periods=min(slow, 50)).mean()
            w = pd.DataFrame(0.0, index=prices.index, columns=cols)
            slot = 1.0 / max(1, len(assets))
            for c in assets:
                cond = (prices[c] > sma_s[c]) & (sma_f[c] > sma_s[c])
                w[c] = np.where(cond, slot, 0.0)
            w[safe] = (1.0 - w[assets].sum(axis=1)).clip(lower=0.0)
            return _causal_rebalance(w, freq)

        if engine == "all_weather_trend_parity":
            assets = _filter_symbols(
                params.get("assets") or params.get("risk_assets"),
                prices,
                ("SPY", "TLT", "IEF", "GLD", "DBC", "VNQ"),
                min_count=3,
            )
            safe = _pick_safe(params.get("safe_asset"), prices, "SHY")
            cols = list(dict.fromkeys([*assets, safe]))
            sma_win = _clamp_int(params.get("sma_window"), 180, 50, 252)
            vol_win = _clamp_int(params.get("vol_window"), 63, 20, 90)

            sma = prices[assets].rolling(sma_win, min_periods=min(sma_win, 50)).mean()
            vol = prices[assets].pct_change().rolling(vol_win, min_periods=min(vol_win, 20)).std()
            inv_vol = (1.0 / vol.replace(0.0, np.nan)).fillna(0.0)
            w = pd.DataFrame(0.0, index=prices.index, columns=cols)
            for idx in range(min(sma_win, len(prices)), len(prices)):
                row_iv = {}
                for c in assets:
                    if pd.notna(sma[c].iloc[idx]) and float(prices[c].iloc[idx]) > float(sma[c].iloc[idx]):
                        iv = float(inv_vol[c].iloc[idx])
                        if iv > 0:
                            row_iv[c] = iv
                if row_iv:
                    tot = sum(row_iv.values())
                    # Scale invested share by breadth fraction so weak regimes stay defensive
                    breadth_scale = len(row_iv) / float(len(assets))
                    for c, iv in row_iv.items():
                        w.iat[idx, cols.index(c)] = breadth_scale * (iv / tot)
                    w.iat[idx, cols.index(safe)] = max(0.0, 1.0 - breadth_scale)
                else:
                    w.iat[idx, cols.index(safe)] = 1.0
            return _causal_rebalance(w, freq)

        # engine == "barbell_defensive"
        safe_core = _filter_symbols(params.get("safe_assets"), prices, ("SHY", "IEF"), min_count=1)
        tactical = _filter_symbols(
            params.get("tactical_assets") or params.get("risk_assets"),
            prices,
            ("DBC", "GLD", "VNQ", "XLE", "XLV", "USMV", "QQQ"),
            min_count=2,
        )
        cols = list(dict.fromkeys([*safe_core, *tactical]))
        core_w = _clamp_float(params.get("core_weight_pct"), 60.0, 30.0, 90.0) / 100.0
        tactical_w = 1.0 - core_w
        sma_win = _clamp_int(params.get("sma_window"), 150, 50, 252)
        mom_win = _clamp_int(params.get("momentum_days"), 126, 21, 252)
        top_n = _clamp_int(params.get("top_n"), 3, 1, 5)

        sma = prices[cols].rolling(sma_win, min_periods=min(sma_win, 50)).mean()
        mom = prices[cols].pct_change(mom_win)
        w = pd.DataFrame(0.0, index=prices.index, columns=cols)
        warmup = max(sma_win, mom_win)
        for idx in range(min(warmup, len(prices)), len(prices)):
            # Allocate core sleeve to strongest safe asset(s)
            safe_vals = [(c, float(mom[c].iloc[idx])) for c in safe_core if pd.notna(mom[c].iloc[idx])]
            best_safe = max(safe_vals, key=lambda kv: kv[1])[0] if safe_vals else safe_core[0]
            w.iat[idx, cols.index(best_safe)] += core_w

            # Allocate tactical sleeve only to assets strictly above SMA with positive momentum
            elig = [
                (c, float(mom[c].iloc[idx]))
                for c in tactical
                if pd.notna(sma[c].iloc[idx])
                and pd.notna(mom[c].iloc[idx])
                and float(prices[c].iloc[idx]) > float(sma[c].iloc[idx])
                and float(mom[c].iloc[idx]) > 0.0
            ]
            elig.sort(key=lambda kv: kv[1], reverse=True)
            chosen = elig[:top_n]
            if chosen:
                each = tactical_w / len(chosen)
                for sym, _ in chosen:
                    w.iat[idx, cols.index(sym)] += each
            else:
                w.iat[idx, cols.index(best_safe)] += tactical_w
        return _causal_rebalance(w, freq)

    return _build


# ---------------------------------------------------------------------------
# Live context packet + 3-CLI prompt & JSON extraction
# ---------------------------------------------------------------------------


def build_council_market_context(prices: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Assemble today's verified empirical snapshot to feed all 3 AI CLIs identically."""
    from src.quant.tournament import get_live_paa_signal, load_latest_tournament_results

    paa = get_live_paa_signal(force_refresh=False)
    tour = load_latest_tournament_results(auto_run_if_missing=False) or {}

    top_strats = []
    for row in (tour.get("strategies") or [])[:10]:
        oos = row.get("oos") or {}
        top_strats.append(
            {
                "id": row.get("strategy_id"),
                "name": row.get("name"),
                "verdict": row.get("verdict"),
                "oos_cagr_pct": oos.get("cagr_pct"),
                "oos_sharpe": oos.get("sharpe"),
                "oos_max_dd_pct": oos.get("max_drawdown_pct"),
                "oos_dsr_pct": oos.get("dsr_pct"),
                "current_signal": row.get("signal_summary"),
            }
        )

    sector_snap = []
    if prices is not None and not prices.empty:
        sma200 = prices.rolling(200, min_periods=100).mean()
        mom63 = prices.pct_change(63)
        for sym in ("SPY", "QQQ", "GLD", "DBC", "VNQ", "TLT", "IEF", "SHY", "BIL", "XLE", "XLV", "XLF", "XLK", "XLU", "XLP", "USMV", "QUAL"):
            if sym in prices.columns and pd.notna(prices[sym].iloc[-1]):
                px = float(prices[sym].iloc[-1])
                s200 = float(sma200[sym].iloc[-1]) if pd.notna(sma200[sym].iloc[-1]) else px
                m63 = float(mom63[sym].iloc[-1]) * 100.0 if pd.notna(mom63[sym].iloc[-1]) else 0.0
                sector_snap.append(
                    {
                        "symbol": sym,
                        "close": round(px, 2),
                        "vs_sma200_pct": round(((px / s200) - 1.0) * 100.0, 2) if s200 > 0 else 0.0,
                        "mom_3m_pct": round(m63, 2),
                    }
                )

    return {
        "as_of_date": paa.get("as_of_date") or tour.get("latest_date") or date.today().isoformat(),
        "paa_live_regime": {
            "regime_label": paa.get("regime_label"),
            "risk_assets_below_sma252": paa.get("risk_assets_below_sma252"),
            "risk_assets_total": paa.get("risk_assets_total"),
            "crash_protection_pct": paa.get("crash_protection_pct"),
            "paa_target_weights_pct": paa.get("target_weights_pct"),
        },
        "etf_snapshot": sector_snap,
        "tournament_top_10_oos_2022_present": top_strats,
        "allowed_etf_universe": list(ALLOWED_COUNCIL_ETFS),
        "allowed_rule_engines": {
            "paa_custom": {"params": ["risk_assets", "safe_assets", "lookback_days", "top_n", "protection_factor", "rebalance_freq"]},
            "vol_target_trend": {"params": ["risk_assets", "safe_asset", "sma_window", "vol_window", "target_vol_pct", "max_weight", "rebalance_freq"]},
            "safe_haven_momentum": {"params": ["offensive_assets", "defensive_assets", "momentum_days", "sma_filter_days", "top_n", "rebalance_freq"]},
            "dual_sma_trend": {"params": ["assets", "fast_sma", "slow_sma", "safe_asset", "rebalance_freq"]},
            "all_weather_trend_parity": {"params": ["assets", "safe_asset", "sma_window", "vol_window", "rebalance_freq"]},
            "barbell_defensive": {"params": ["safe_assets", "tactical_assets", "core_weight_pct", "sma_window", "momentum_days", "top_n", "rebalance_freq"]},
        },
    }


def _build_council_prompt(member_key: str, context: Dict[str, Any]) -> str:
    role_angles = {
        "claude": (
            "Sen kurumsal makro-risk ve düşüş koruması (tail-risk & Sharpe optimizasyonu) odaklı "
            "Claude Quant Portfolio Manager'sın. Özellikle çöküş koruması ve yüksek DSR dengesine odaklan."
        ),
        "codex": (
            "Sen sistematik trend-takibi, volatilite hedefleme ve düşük devir (low-turnover) odaklı "
            "Codex Quantitative Engineer'sın. Net maliyet sonrası tutarlı bileşik getiriye odaklan."
        ),
        "gemini": (
            "Sen çoklu varlık rotasyonu, emtia/sektör momentumu ve adaptif barbell portföy tasarımı odaklı "
            "Gemini Tactical Asset Allocator'sın. Mevcut piyasa rejiminde sermayeyi koruyup trend dönünce "
            "hızlı yakalayacak özgün bir kural tasarla."
        ),
    }
    return (
        f"{role_angles.get(member_key, '')}\n\n"
        "Aşağıdaki BUGÜNKÜ gerçek piyasa verilerine ve 25 stratejilik OOS turnuva sonuçlarına dayanarak, "
        "bugünden itibaren her gün otomatik sanal portföy defterinde ($10,000 başlangıç, 5 bps maliyet, "
        "sıfır lookahead) takip edilecek KENDİ ÖZGÜN, KURAL TABANLI stratejini belirle.\n\n"
        "KESİN KURALLAR:\n"
        "1. Sadece geçerli TEK BİR JSON nesnesi döndür (Markdown çiti veya ek açıklama yazma).\n"
        "2. `rule_engine` alanı mutlaka `allowed_rule_engines` anahtarlarından biri olmalı.\n"
        "3. Tüm ETF sembolleri mutlaka `allowed_etf_universe` içinden seçilmeli.\n"
        "4. `strategy_name`, `thesis` ve `risk_rules` alanları net ve kısa Türkçe olmalı.\n"
        "5. `rebalance_mode` alanı `'monthly'` veya `'daily'` olmalı (genellikle `'monthly'` maliyet-verimli).\n\n"
        "BEKLENEN JSON ŞEMASI:\n"
        "{\n"
        '  "strategy_name": "Kısa Türkçe strateji adı",\n'
        '  "rule_engine": "vol_target_trend | safe_haven_momentum | paa_custom | dual_sma_trend | all_weather_trend_parity | barbell_defensive",\n'
        '  "rebalance_mode": "monthly",\n'
        '  "params": { ... seçtiğin rule_engine parametreleri ... },\n'
        '  "thesis": "2-3 cümlelik somut piyasa gerekçesi",\n'
        '  "risk_rules": "Düşüş kalkanı ve risk kontrol özeti"\n'
        "}\n\n"
        f"CANLI PİYASA & TURNUVA BAĞLAMI:\n{json.dumps(context, ensure_ascii=False)}"
    )


def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    text = str(raw_text or "").strip()
    if not text:
        return None
    # Strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    # Try direct load
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    # Extract outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            try:
                from json_repair import repair_json

                repaired = json.loads(repair_json(candidate))
                if isinstance(repaired, dict):
                    return repaired
            except Exception:
                pass
    return None


def invoke_council_cli(
    member_key: str,
    prompt: str,
    *,
    timeout_s: float = 120.0,
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke Claude CLI, Codex CLI, or Gemini CLI headless and extract its JSON Strategy Charter."""
    meta = COUNCIL_MEMBER_META[member_key]
    binary = resolve_cli_binary(meta["binary"], env_override=meta["path_env"])
    if not binary:
        return {"ok": False, "member": member_key, "error": f"{meta['engine_label']} bulunamadı."}

    model = (model_override or os.getenv(meta["model_env"]) or "").strip() or None
    env = build_cli_subprocess_env()
    proc: Optional[subprocess.Popen] = None
    tmp_out: Optional[Path] = None

    try:
        if member_key == "claude":
            cmd = [
                binary,
                "-p",
                "--output-format",
                "json",
                "--tools",
                "",
                "--permission-mode",
                "dontAsk",
                "--no-session-persistence",
            ]
            if model:
                cmd.extend(["--model", model])
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout_s)
            if proc.returncode != 0:
                return {"ok": False, "member": member_key, "error": (stderr or stdout or f"exit {proc.returncode}")[-400:]}
            envelope = _extract_json_object(stdout) or {}
            inner_text = envelope.get("result") if isinstance(envelope.get("result"), str) else stdout
            charter = _extract_json_object(inner_text)
            used_model = model or (next(iter((envelope.get("modelUsage") or {}).keys()), None) if isinstance(envelope.get("modelUsage"), dict) else None)
            if not charter:
                return {"ok": False, "member": member_key, "error": f"Geçerli JSON alınamadı: {inner_text[:250]}"}
            return {"ok": True, "member": member_key, "model": used_model, "charter": charter}

        if member_key == "codex":
            fd, tmp_name = tempfile.mkstemp(prefix="dsa_codex_council_", suffix=".txt")
            os.close(fd)
            tmp_out = Path(tmp_name)
            cmd = [
                binary,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-o",
                str(tmp_out),
            ]
            if model:
                cmd.extend(["-m", model])
            cmd.append("-")
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout_s)
            raw_out = tmp_out.read_text(encoding="utf-8", errors="replace").strip() if tmp_out.is_file() else ""
            if proc.returncode != 0 and not raw_out:
                return {"ok": False, "member": member_key, "error": (stderr or stdout or f"exit {proc.returncode}")[-400:]}
            charter = _extract_json_object(raw_out or stdout)
            m_match = re.search(r"^model:\s*(.+)$", (stdout or "") + "\n" + (stderr or ""), flags=re.MULTILINE)
            used_model = model or (m_match.group(1).strip() if m_match else None)
            if not charter:
                return {"ok": False, "member": member_key, "error": f"Geçerli JSON alınamadı: {(raw_out or stdout)[:250]}"}
            return {"ok": True, "member": member_key, "model": used_model, "charter": charter}

        # member_key == "gemini"
        cmd = [binary, "-p", "", "--output-format", "json", "--skip-trust"]
        if model:
            cmd.extend(["-m", model])
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout_s)
        envelope = _extract_json_object(stdout) or {}
        if proc.returncode != 0 and "response" not in envelope:
            err_msg = (envelope.get("error") or {}).get("message") if isinstance(envelope.get("error"), dict) else None
            return {"ok": False, "member": member_key, "error": str(err_msg or stderr or stdout or f"exit {proc.returncode}")[-400:]}
        inner_text = envelope.get("response") if isinstance(envelope.get("response"), str) else stdout
        charter = _extract_json_object(inner_text)
        used_model = model
        if not used_model and isinstance(envelope.get("stats"), dict):
            models_map = (envelope["stats"].get("models") or {})
            if isinstance(models_map, dict) and models_map:
                used_model = next(iter(models_map.keys()))
        if not charter:
            return {"ok": False, "member": member_key, "error": f"Geçerli JSON alınamadı: {inner_text[:250]}"}
        return {"ok": True, "member": member_key, "model": used_model, "charter": charter}

    except subprocess.TimeoutExpired:
        terminate_process_tree(proc)
        return {"ok": False, "member": member_key, "error": f"Zaman aşımı ({timeout_s:.0f}s)"}
    except Exception as exc:  # noqa: BLE001
        terminate_process_tree(proc)
        return {"ok": False, "member": member_key, "error": str(exc)}
    finally:
        if tmp_out and tmp_out.is_file():
            try:
                tmp_out.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Persistence + OOS Validation + Daily StrategyPaperBook Tracking
# ---------------------------------------------------------------------------


def load_council_charters(book_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(book_dir or DEFAULT_BOOK_DIR) / COUNCIL_CHARTERS_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_council_charters(payload: Dict[str, Any], book_dir: Optional[Path] = None) -> Path:
    target_dir = Path(book_dir or DEFAULT_BOOK_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / COUNCIL_CHARTERS_FILENAME
    fd, tmp_name = tempfile.mkstemp(dir=str(target_dir), prefix=".ai_council_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_name, path)
    return path


def evaluate_and_register_charter(
    member_key: str,
    raw_charter: Dict[str, Any],
    prices: pd.DataFrame,
    *,
    model: Optional[str] = None,
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    book_dir: Optional[Path] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Validate an AI CLI's strategy charter with OOS backtest and initialize its live StrategyPaperBook."""
    meta = COUNCIL_MEMBER_META[member_key]
    engine = str(raw_charter.get("rule_engine") or "vol_target_trend").strip().lower()
    if engine not in ALLOWED_RULE_ENGINES:
        engine = "vol_target_trend"
    rebalance_mode = str(raw_charter.get("rebalance_mode") or "monthly").strip().lower()
    if rebalance_mode not in ("monthly", "daily"):
        rebalance_mode = "monthly"
    params = raw_charter.get("params") if isinstance(raw_charter.get("params"), dict) else {}

    normalized_charter: Dict[str, Any] = {
        "member_key": member_key,
        "strategy_key": meta["strategy_key"],
        "strategy_id": f"COUNCIL_{member_key.upper()}",
        "engine_label": meta["engine_label"],
        "model": model or "cli-default",
        "strategy_name": str(raw_charter.get("strategy_name") or f"{meta['engine_label']} Stratejisi").strip()[:90],
        "rule_engine": engine,
        "rebalance_mode": rebalance_mode,
        "params": params,
        "thesis": str(raw_charter.get("thesis") or "").strip()[:600],
        "risk_rules": str(raw_charter.get("risk_rules") or "").strip()[:400],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    weight_fn = compile_council_weight_fn(normalized_charter)
    weights_df = weight_fn(prices)
    spec = StrategySpec(
        strategy_id=normalized_charter["strategy_id"],
        name=f"{meta['engine_label']} · {normalized_charter['strategy_name']}",
        universe="us_etf",
        category="AI Council",
        description=normalized_charter["thesis"],
        cost_bps=cost_bps,
        trading_days_per_year=252,
    )
    bt = backtest_weight_matrix(prices, weights_df, spec, oos_start=DEFAULT_OOS_START, n_trials=28)
    verdict = classify_strategy_verdict(bt.oos, universe="us_etf")
    normalized_charter["oos_backtest"] = bt.oos.to_dict()
    normalized_charter["verdict"] = verdict
    normalized_charter["live_signal_summary"] = bt.signal_summary
    normalized_charter["live_target_weights_pct"] = dict(bt.current_weights)

    # Initialize / step today's live StrategyPaperBook
    book = QuantAllocationPaperBook(
        name=meta["book_name"],
        strategy_key=meta["strategy_key"],
        strategy_id=normalized_charter["strategy_id"],
        label=f"{meta['engine_label']} · {normalized_charter['strategy_name']}",
        benchmark_symbol="SPY",
        initial_capital=initial_capital,
        cost_bps=cost_bps,
        rebalance_mode=rebalance_mode,
        book_dir=book_dir or DEFAULT_BOOK_DIR,
    )
    step_res = book.step(prices, weight_fn, today=today)
    summary = book.summary()
    summary["processed_days"] = int(step_res.get("processed_days") or 0)
    summary["new_trades"] = list(step_res.get("new_trades") or [])
    summary["report_text"] = format_quant_book_report(summary)
    summary["council_meta"] = {
        "member_key": member_key,
        "engine_label": meta["engine_label"],
        "model": normalized_charter["model"],
        "rule_engine": engine,
        "thesis": normalized_charter["thesis"],
        "risk_rules": normalized_charter["risk_rules"],
        "oos_backtest": normalized_charter["oos_backtest"],
        "verdict": normalized_charter["verdict"],
    }

    return {"charter": normalized_charter, "book_summary": summary}


def convene_ai_strategy_council(
    *,
    members: Sequence[str] = ("claude", "codex", "gemini"),
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    timeout_s: float = 120.0,
    model_overrides: Optional[Dict[str, str]] = None,
    force_refresh_prices: bool = False,
    book_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Convene Claude CLI, Codex CLI, and Gemini CLI to design, backtest, and start tracking strategies."""
    from concurrent.futures import ThreadPoolExecutor

    prices = load_council_etf_prices(force_refresh=force_refresh_prices)
    if prices.empty:
        return {"ok": False, "error": "ETF fiyat verisi yüklenemedi.", "members": {}}

    context = build_council_market_context(prices)
    overrides = model_overrides or {}
    valid_members = [m for m in members if m in COUNCIL_MEMBER_META]

    def _call_one(m: str) -> Dict[str, Any]:
        prompt = _build_council_prompt(m, context)
        return invoke_council_cli(m, prompt, timeout_s=timeout_s, model_override=overrides.get(m))

    raw_results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(valid_members))) as pool:
        futs = {m: pool.submit(_call_one, m) for m in valid_members}
        for m, fut in futs.items():
            raw_results[m] = fut.result()

    persisted = load_council_charters(book_dir)
    charters_map: Dict[str, Any] = dict(persisted.get("members") or {})
    status_report: Dict[str, Any] = {}

    for m in valid_members:
        res = raw_results[m]
        if not res.get("ok"):
            status_report[m] = {"ok": False, "error": res.get("error")}
            continue
        evaluated = evaluate_and_register_charter(
            m,
            res["charter"],
            prices,
            model=res.get("model"),
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            book_dir=book_dir,
        )
        charters_map[m] = evaluated["charter"]
        status_report[m] = {
            "ok": True,
            "charter": evaluated["charter"],
            "book": evaluated["book_summary"],
        }

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of_date": context["as_of_date"],
        "members": charters_map,
    }
    save_council_charters(payload, book_dir)
    return {
        "ok": any(v.get("ok") for v in status_report.values()),
        "as_of_date": context["as_of_date"],
        "results": status_report,
        "active_charters": list(charters_map.keys()),
    }


def step_active_council_books(
    *,
    prices: Optional[pd.DataFrame] = None,
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    force_rebalance: bool = False,
    force_refresh_prices: bool = False,
    book_dir: Optional[Path] = None,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Advance all persisted AI Council StrategyPaperBooks forward by completed daily closes."""
    stored = load_council_charters(book_dir)
    members = stored.get("members") or {}
    if not members:
        return []
    price_frame = prices if prices is not None else load_council_etf_prices(force_refresh=force_refresh_prices)
    if price_frame is None or price_frame.empty:
        return []

    out: List[Dict[str, Any]] = []
    for member_key, charter in members.items():
        if member_key not in COUNCIL_MEMBER_META or not isinstance(charter, dict):
            continue
        meta = COUNCIL_MEMBER_META[member_key]
        weight_fn = compile_council_weight_fn(charter)
        book = QuantAllocationPaperBook(
            name=meta["book_name"],
            strategy_key=meta["strategy_key"],
            strategy_id=charter.get("strategy_id") or f"COUNCIL_{member_key.upper()}",
            label=f"{meta['engine_label']} · {charter.get('strategy_name') or meta['engine_label']}",
            benchmark_symbol="SPY",
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            rebalance_mode=str(charter.get("rebalance_mode") or "monthly"),
            book_dir=book_dir or DEFAULT_BOOK_DIR,
        )
        step_res = book.step(price_frame, weight_fn, today=today, force_rebalance=force_rebalance)
        summary = book.summary()
        summary["processed_days"] = int(step_res.get("processed_days") or 0)
        summary["new_trades"] = list(step_res.get("new_trades") or [])
        summary["report_text"] = format_quant_book_report(summary)
        summary["council_meta"] = {
            "member_key": member_key,
            "engine_label": meta["engine_label"],
            "model": charter.get("model"),
            "rule_engine": charter.get("rule_engine"),
            "thesis": charter.get("thesis"),
            "risk_rules": charter.get("risk_rules"),
            "oos_backtest": charter.get("oos_backtest"),
            "verdict": charter.get("verdict"),
        }
        out.append(summary)
    return out


def get_active_council_books_status(
    *,
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    book_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Read all persisted AI Council StrategyPaperBooks without network I/O."""
    stored = load_council_charters(book_dir)
    members = stored.get("members") or {}
    out: List[Dict[str, Any]] = []
    for member_key, charter in members.items():
        if member_key not in COUNCIL_MEMBER_META or not isinstance(charter, dict):
            continue
        meta = COUNCIL_MEMBER_META[member_key]
        book = QuantAllocationPaperBook(
            name=meta["book_name"],
            strategy_key=meta["strategy_key"],
            strategy_id=charter.get("strategy_id") or f"COUNCIL_{member_key.upper()}",
            label=f"{meta['engine_label']} · {charter.get('strategy_name') or meta['engine_label']}",
            benchmark_symbol="SPY",
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            rebalance_mode=str(charter.get("rebalance_mode") or "monthly"),
            book_dir=book_dir or DEFAULT_BOOK_DIR,
        )
        summary = book.summary()
        summary["processed_days"] = 0
        summary["new_trades"] = []
        summary["report_text"] = format_quant_book_report(summary)
        summary["council_meta"] = {
            "member_key": member_key,
            "engine_label": meta["engine_label"],
            "model": charter.get("model"),
            "rule_engine": charter.get("rule_engine"),
            "thesis": charter.get("thesis"),
            "risk_rules": charter.get("risk_rules"),
            "oos_backtest": charter.get("oos_backtest"),
            "verdict": charter.get("verdict"),
        }
        out.append(summary)
    return out
