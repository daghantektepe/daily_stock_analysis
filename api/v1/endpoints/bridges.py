# -*- coding: utf-8 -*-
"""API endpoints for Binance Spot, TEFAS, TCMB EVDS2, and broker CSV bridges."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.bridges import (
    AdapterPaperOrderRequest,
    AdapterPreviewRequest,
    AdapterPreviewResponse,
    BinancePreviewResponse,
    BinancePreviewTicker,
    BridgeItemStatus,
    BridgesStatusResponse,
    BrokerAdapterHealthItem,
    BrokerAdaptersResponse,
    MacroTrResponse,
    PurchasePowerResult,
    TefasFundItem,
    TefasFundsResponse,
)
from data_provider.binance_fetcher import BinanceFetcher
from data_provider.evds_fetcher import EvdsMacroFetcher, compute_real_purchase_power_tr
from data_provider.tefas_fetcher import TefasFetcher
from src.brokers.base import BrokerSecurityError, read_broker_audit_tail
from src.brokers.binance.client import BinanceBrokerError, BinanceClient, ccxt_available
from src.brokers.registry import (
    get_broker_registry,
    list_broker_statuses,
    resolve_strategy_target_weights,
)
from src.config import get_config
from src.services.portfolio_import_service import PortfolioImportService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/status",
    response_model=BridgesStatusResponse,
    summary="List status and safety lock state of all external data & broker bridges",
)
def get_bridges_status(
    check_live: bool = Query(False, description="When true, ping public endpoints (Binance time / TRY=X)"),
) -> BridgesStatusResponse:
    cfg = get_config()
    binance_client = BinanceClient.from_config(cfg)
    importer = PortfolioImportService()
    brokers = importer.list_supported_brokers()

    binance_reachable: Optional[bool] = None
    if check_live:
        try:
            binance_reachable = binance_client.get_server_time() > 0
        except Exception:
            binance_reachable = False

    alpaca_configured = bool(getattr(cfg, "alpaca_api_key", None) and getattr(cfg, "alpaca_secret_key", None))
    alpaca_paper = bool(getattr(cfg, "alpaca_paper", True))
    alpaca_auto = bool(getattr(cfg, "alpaca_auto_execute", False))

    evds_configured = bool(getattr(cfg, "evds_api_key", None))
    evds_reachable: Optional[bool] = None
    if check_live:
        try:
            snap = EvdsMacroFetcher.from_config(cfg).get_macro_snapshot()
            evds_reachable = snap.get("usd_try") is not None
        except Exception:
            evds_reachable = False

    bridges: List[BridgeItemStatus] = [
        BridgeItemStatus(
            id="binance",
            name="Binance Spot & Testnet",
            kind="crypto_data_and_sandbox",
            configured=binance_client.is_configured,
            sandbox_or_readonly=binance_client.testnet or not binance_client.auto_execute,
            mode_label="Testnet Sanal" if binance_client.testnet else "Canlı Salt-Okunur" if not binance_client.auto_execute else "Canlı",
            live_reachable=binance_reachable,
            note="Kripto 5-SMA verisi herkese açık uçtan ücretsiz gelir; emirler Testnet + manuel onay kilitlidir.",
            details={
                "testnet": binance_client.testnet,
                "auto_execute": binance_client.auto_execute,
                "live_trading_confirmed": binance_client.live_trading_confirmed,
                "ccxt_installed": ccxt_available(),
            },
        ),
        BridgeItemStatus(
            id="tefas",
            name="TEFAS Yatırım Fonları",
            kind="turkish_funds_data",
            configured=True,
            sandbox_or_readonly=True,
            mode_label="Canlı Resmi API + 6s Önbellek",
            live_reachable=None,
            note="PPF, Altın, BIST ve Yabancı Teknoloji fonlarının birim fiyat ve büyüklüklerini çeker.",
        ),
        BridgeItemStatus(
            id="evds",
            name="TCMB EVDS2 Makro & TÜFE",
            kind="turkish_macro_data",
            configured=evds_configured,
            sandbox_or_readonly=True,
            mode_label="EVDS2 Resmi" if evds_configured else "TRY=X Yedek (EVDS Key Yok)",
            live_reachable=evds_reachable,
            note="USD/TRY (TP.DK.USD.S.YTL) + TÜFE (TP.FG.J0) ile nominal vs reel alım gücü hesaplar.",
        ),
        BridgeItemStatus(
            id="alpaca",
            name="Alpaca ABD Hisse & ETF",
            kind="us_broker_paper",
            configured=alpaca_configured,
            sandbox_or_readonly=alpaca_paper or not alpaca_auto,
            mode_label="Paper Sanal" if alpaca_paper else "Canlı (Kilitli)",
            note="Meta-Portföy A v2 ve PAA v2 ABD ETF sepeti için sanal emir önizleme ve kayma ölçümü.",
            details={
                "paper": alpaca_paper,
                "auto_execute": alpaca_auto,
            },
        ),
        BridgeItemStatus(
            id="csv_imports",
            name="Midas / Binance / Genel CSV & Excel İçe Aktarım",
            kind="portfolio_import",
            configured=True,
            sandbox_or_readonly=True,
            mode_label=f"{len(brokers)} Format Hazır",
            note="Midas BIST, Midas ABD, Binance Spot ve Türkçe Excel (.xlsx / .csv) işlem geçmişini tek tıkla aktarır.",
            details={"brokers": [b["broker"] for b in brokers]},
        ),
    ]
    return BridgesStatusResponse(ok=True, checked_live=check_live, bridges=bridges)


@router.get(
    "/tefas",
    response_model=TefasFundsResponse,
    summary="Fetch live or 6h-cached TEFAS mutual fund snapshots",
)
def get_tefas_funds(
    bucket: Optional[str] = Query(None, description="Filter by bucket: ppf, altin, bist, yabanci, degisken_doviz"),
    codes: Optional[str] = Query(None, description="Comma-separated TEFAS fund codes, e.g. PPZ,AFT,TCA"),
    force_refresh: bool = Query(False, description="Bypass 6-hour disk cache"),
) -> TefasFundsResponse:
    code_list = [c.strip().upper() for c in codes.split(",") if c.strip()] if codes else None
    try:
        fetcher = TefasFetcher()
        rows = fetcher.fetch_curated_funds(bucket=bucket, codes=code_list, force_refresh=force_refresh)
        items = [TefasFundItem(**row) for row in rows]
        live_count = sum(1 for item in items if item.source in {"tefas_live", "tefas_cached"})
        return TefasFundsResponse(ok=True, count=len(items), live_count=live_count, funds=items)
    except Exception as exc:
        logger.exception("[bridges/tefas] fetch failed")
        raise HTTPException(status_code=500, detail=f"TEFAS fetch failed: {exc}") from exc


@router.get(
    "/macro-tr",
    response_model=MacroTrResponse,
    summary="Fetch USD/TRY and TÜFE CPI snapshot from TCMB EVDS2 (or TRY=X fallback)",
)
def get_macro_tr(
    nominal_return_pct: Optional[float] = Query(None, description="Optional nominal TRY return (%) to adjust"),
    force_refresh: bool = Query(False, description="Bypass 12-hour disk cache"),
) -> MacroTrResponse:
    fetcher = EvdsMacroFetcher.from_config()
    snap = fetcher.get_macro_snapshot(force_refresh=force_refresh)
    pp: Optional[PurchasePowerResult] = None
    if nominal_return_pct is not None:
        calc = compute_real_purchase_power_tr(
            nominal_return_pct=nominal_return_pct,
            usd_try_change_pct=snap.get("usd_try_1y_change_pct"),
            cpi_yoy_pct=snap.get("cpi_yoy_pct"),
        )
        pp = PurchasePowerResult(**calc)
    return MacroTrResponse(ok=True, purchasing_power=pp, **snap)


@router.get(
    "/binance/preview",
    response_model=BinancePreviewResponse,
    summary="Read-only Binance Spot public market preview + optional Testnet account balances",
)
def get_binance_preview(
    assets: str = Query("BTC-USD,ETH-USD", description="Comma-separated crypto pairs"),
    include_account: bool = Query(False, description="Include Testnet/Spot read-only balance if API keys exist"),
) -> BinancePreviewResponse:
    cfg = get_config()
    client = BinanceClient.from_config(cfg)
    fetcher = BinanceFetcher(client=client)
    asset_list = [a.strip() for a in assets.split(",") if a.strip()] or ["BTC-USD", "ETH-USD"]
    snapshots = fetcher.fetch_live_snapshot(asset_list)
    tickers = [BinancePreviewTicker(**row) for row in snapshots]

    account_info = None
    if include_account and client.is_configured:
        try:
            account_info = client.get_account_summary()
        except BinanceBrokerError as exc:
            account_info = {"error": str(exc)}

    return BinancePreviewResponse(
        ok=True,
        testnet=client.testnet,
        configured=client.is_configured,
        auto_execute=client.auto_execute,
        tickers=tickers,
        account=account_info,
    )


@router.get(
    "/adapters",
    response_model=BrokerAdaptersResponse,
    summary="List unified BrokerAdapter instances and recent audit log tail",
)
def get_unified_adapters(
    tail: int = Query(12, ge=1, le=50),
) -> BrokerAdaptersResponse:
    statuses = [BrokerAdapterHealthItem(**item) for item in list_broker_statuses()]
    audit = read_broker_audit_tail(limit=tail)
    return BrokerAdaptersResponse(ok=True, adapters=statuses, audit_tail=audit)


@router.post(
    "/adapters/preview",
    response_model=AdapterPreviewResponse,
    summary="Calculate safety-locked rebalance preview orders across Alpaca, Binance Testnet, AlgoLab, or IBKR",
)
def preview_adapter_rebalance(req: AdapterPreviewRequest) -> AdapterPreviewResponse:
    registry = get_broker_registry()
    broker_key = (req.broker_id or "alpaca").strip().lower()
    adapter = registry.get(broker_key)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Unknown broker adapter '{broker_key}'")

    strategy_key = (req.strategy_key or "meta_a").strip().lower()
    weights = req.target_weights or resolve_strategy_target_weights(strategy_key)
    plan = adapter.preview_rebalance_plan(weights, capital=req.capital)
    orders = list(plan.get("orders") or [])
    currency = str(plan.get("currency") or "USD")
    lines = [
        f"{broker_key.upper()} EMİR PLANI ({strategy_key}, Sermaye: {plan.get('capital')} {currency}) [Otomatik gönderim YOK / Manuel Onaylı]:"
    ]
    for ord_item in orders:
        amt = ord_item.get("notional_usdt") or ord_item.get("delta_notional") or ord_item.get("target_notional") or 0
        lines.append(
            f"- {ord_item.get('symbol')}: {ord_item.get('side')} (~{abs(float(amt)):,.2f} {ord_item.get('currency') or currency})"
        )

    return AdapterPreviewResponse(
        ok=True,
        broker_id=broker_key,
        strategy_key=strategy_key,
        sandbox=bool(plan.get("sandbox", adapter.is_sandbox)),
        read_only_enforced=bool(plan.get("read_only_enforced", adapter.read_only_enforced)),
        currency=currency,
        capital=float(plan.get("capital") or req.capital or 0.0),
        target_weights={str(k): float(v) for k, v in weights.items()},
        orders=orders,
        copy_text="\n".join(lines),
    )


@router.post(
    "/adapters/{broker_id}/paper-order",
    summary="Submit ONE explicitly confirmed sandbox order to Alpaca Paper or Binance Testnet",
)
def submit_adapter_paper_order(broker_id: str, req: AdapterPaperOrderRequest) -> dict:
    registry = get_broker_registry()
    broker_key = (broker_id or "").strip().lower()
    adapter = registry.get(broker_key)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Unknown broker adapter '{broker_key}'")

    try:
        result = adapter.submit_paper_order(
            {
                "symbol": req.symbol,
                "side": req.side,
                "quantity": req.quantity,
                "qty": req.quantity,
                "quote_order_qty": req.quote_order_qty,
                "test_only": req.test_only,
            },
            confirmed=req.confirmed,
        )
        return {"ok": True, **result}
    except BrokerSecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
