# -*- coding: utf-8 -*-
"""Portfolio CSV import service with extensible parser registry."""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data_provider.base import canonical_stock_code
from src.repositories.portfolio_repo import PortfolioRepository
from src.services.portfolio_service import (
    PortfolioBusyError,
    PortfolioConflictError,
    PortfolioOversellError,
    PortfolioService,
)

logger = logging.getLogger(__name__)

_TR_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{2,5}$")


@dataclass(frozen=True)
class CsvParserSpec:
    """CSV/XLSX parser specification for one broker."""

    broker: str
    aliases: Tuple[str, ...]
    display_name: str
    column_hints: Dict[str, Tuple[str, ...]]
    default_currency: Optional[str] = None
    default_market_suffix: Optional[str] = None
    sample_csv: str = ""


DEFAULT_PARSER_SPECS: Tuple[CsvParserSpec, ...] = (
    CsvParserSpec(
        broker="huatai",
        aliases=(),
        display_name="华泰",
        column_hints={
            "trade_date": ("成交日期", "成交时间", "发生日期", "日期"),
            "symbol": ("证券代码", "股票代码", "代码"),
            "side": ("买卖标志", "买卖方向", "操作"),
            "quantity": ("成交数量", "数量", "成交股数"),
            "price": ("成交均价", "成交价格", "价格", "成交价", "均价"),
            "trade_uid": ("成交编号", "成交序号", "流水号"),
        },
        default_currency="CNY",
        sample_csv=(
            "成交日期,证券代码,买卖标志,成交数量,成交均价,成交编号,手续费,印花税\n"
            "2026-11-18,600519,买入,100,1520.00,HT-20261118-01,5.0,0.0\n"
        ),
    ),
    CsvParserSpec(
        broker="citic",
        aliases=("zhongxin",),
        display_name="中信",
        column_hints={
            "trade_date": ("发生日期", "成交日期", "日期"),
            "symbol": ("证券代码", "股票代码", "代码"),
            "side": ("买卖方向", "买卖标志", "业务名称"),
            "quantity": ("成交数量", "数量", "成交股数"),
            "price": ("成交价格", "成交均价", "价格", "成交价"),
            "trade_uid": ("合同编号", "成交编号", "委托编号"),
        },
        default_currency="CNY",
        sample_csv=(
            "发生日期,证券代码,买卖方向,成交数量,成交价格,合同编号\n"
            "2026-11-18,000001,买入,200,11.25,ZX-001\n"
        ),
    ),
    CsvParserSpec(
        broker="cmb",
        aliases=("zhaoshang", "cmbchina"),
        display_name="招商",
        column_hints={
            "trade_date": ("日期", "成交日期", "发生日期"),
            "symbol": ("证券代码", "股票代码", "代码"),
            "side": ("交易方向", "买卖方向", "买卖标志"),
            "quantity": ("成交股数", "成交数量", "数量"),
            "price": ("成交价", "成交价格", "成交均价", "均价"),
            "trade_uid": ("流水号", "成交编号", "成交序号"),
        },
        default_currency="CNY",
        sample_csv=(
            "日期,证券代码,交易方向,成交股数,成交价,流水号\n"
            "2026-11-18,600036,买入,100,36.80,CMB-001\n"
        ),
    ),
    CsvParserSpec(
        broker="midas_bist",
        aliases=("midas", "midas_tr"),
        display_name="Midas BIST",
        column_hints={
            "trade_date": ("İşlem Tarihi", "Islem Tarihi", "Tarih", "Takas Tarihi", "Date"),
            "symbol": ("Hisse Kodu", "Sembol", "Varlık", "Varlik", "Enstrüman", "Symbol", "Ticker"),
            "side": ("İşlem Türü", "Islem Turu", "Yön", "Yon", "Tip", "İşlem", "Side", "Type"),
            "quantity": ("Adet", "Lot", "Miktar", "Quantity", "Amount"),
            "price": ("Birim Fiyat", "Fiyat", "İşlem Fiyatı", "Price", "Avg Price"),
            "trade_uid": ("Referans No", "Emir No", "İşlem No", "Order ID", "Ref"),
        },
        default_currency="TRY",
        default_market_suffix=".IS",
        sample_csv=(
            "İşlem Tarihi;Hisse Kodu;İşlem Türü;Adet;Birim Fiyat;Komisyon;Referans No\n"
            "20.11.2026;THYAO;Alış;10;312,50;0,00;MDS-BIST-001\n"
            "20.11.2026;TUPRS.IS;Alış;5;158,40;0,00;MDS-BIST-002\n"
        ),
    ),
    CsvParserSpec(
        broker="midas_us",
        aliases=("midas_abd", "midas_usa"),
        display_name="Midas ABD / ETF",
        column_hints={
            "trade_date": ("Transaction Date", "Trade Date", "İşlem Tarihi", "Islem Tarihi", "Date", "Tarih"),
            "symbol": ("Ticker", "Symbol", "Hisse", "Hisse Kodu", "Sembol"),
            "side": ("Side", "Type", "Transaction Type", "İşlem Türü", "Islem Turu", "Action"),
            "quantity": ("Shares", "Quantity", "Qty", "Adet", "Miktar"),
            "price": ("Execution Price", "Price", "Unit Price", "Birim Fiyat", "Fiyat"),
            "trade_uid": ("Order ID", "Trade ID", "Ref", "Referans No", "Emir No"),
        },
        default_currency="USD",
        sample_csv=(
            "Transaction Date,Ticker,Side,Shares,Execution Price,Fee,Order ID\n"
            "2026-11-20,BIL,Buy,20,91.50,1.50,MDS-US-001\n"
            "2026-11-20,UUP,Buy,15,28.90,1.50,MDS-US-002\n"
        ),
    ),
    CsvParserSpec(
        broker="binance_spot",
        aliases=("binance", "binance_tr"),
        display_name="Binance Spot / TR",
        column_hints={
            "trade_date": ("Date(UTC)", "Date", "Time", "Tarih", "Trade Time"),
            "symbol": ("Pair", "Market", "Symbol", "Çift", "Sembol"),
            "side": ("Side", "Type", "Yön", "Operation"),
            "quantity": ("Executed", "Amount", "Qty", "Quantity", "Miktar"),
            "price": ("Price", "AvgPrice", "Average Price", "Fiyat"),
            "trade_uid": ("Order ID", "Trade ID", "Id", "No"),
        },
        default_currency="USDT",
        sample_csv=(
            "Date(UTC),Pair,Side,Price,Executed,Amount,Fee,Order ID\n"
            "2026-11-20 14:30:00,BTCUSDT,BUY,88500.00,0.015BTC,1327.50USDT,1.32,BNC-001\n"
            "2026-11-20 14:35:00,ETHUSDT,BUY,3120.00,0.25ETH,780.00USDT,0.78,BNC-002\n"
        ),
    ),
    CsvParserSpec(
        broker="generic_tr",
        aliases=("genel_tr", "banka", "tr_csv"),
        display_name="Genel TR (CSV / Excel)",
        column_hints={
            "trade_date": ("Tarih", "İşlem Tarihi", "Trade Date", "Date"),
            "symbol": ("Kod", "Sembol", "Hisse", "Hisse Kodu", "Symbol", "Ticker"),
            "side": ("İşlem", "İşlem Türü", "Yön", "Side", "Type"),
            "quantity": ("Adet", "Lot", "Miktar", "Quantity", "Shares"),
            "price": ("Fiyat", "Birim Fiyat", "Price"),
            "trade_uid": ("İşlem No", "Referans", "Ref", "Trade ID", "Order ID"),
        },
        default_currency="TRY",
        sample_csv=(
            "Tarih;Kod;İşlem;Adet;Fiyat;Komisyon;Para Birimi;İşlem No\n"
            "20.11.2026;ASELS.IS;AL;25;72,40;1,50;TRY;TR-001\n"
            "20.11.2026;SPY;BUY;2;590,00;1,50;USD;TR-002\n"
        ),
    ),
)


class PortfolioImportService:
    """Parse broker CSV and commit normalized trade records with dedup."""
    _shared_parser_registry: Dict[str, CsvParserSpec] = {}
    _shared_broker_alias_map: Dict[str, str] = {}
    _shared_registry_initialized: bool = False

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        repo: Optional[PortfolioRepository] = None,
    ):
        self.portfolio_service = portfolio_service or PortfolioService()
        self.repo = repo or PortfolioRepository()
        self._parser_registry = self.__class__._shared_parser_registry
        self._broker_alias_map = self.__class__._shared_broker_alias_map
        if not self.__class__._shared_registry_initialized:
            self._init_default_parsers()
            self.__class__._shared_registry_initialized = True

    def _init_default_parsers(self) -> None:
        for spec in DEFAULT_PARSER_SPECS:
            self.register_parser(spec)

    def register_parser(self, spec: CsvParserSpec) -> None:
        """Register or replace one broker parser spec."""
        broker = (spec.broker or "").strip().lower()
        if not broker:
            raise ValueError("broker is required")
        new_aliases = tuple(sorted({alias.strip().lower() for alias in spec.aliases if alias}))
        for alias in new_aliases:
            if alias == broker:
                raise ValueError(f"alias '{alias}' cannot be the same as broker id")
            existing_target = self._broker_alias_map.get(alias)
            if existing_target and existing_target != broker:
                raise ValueError(
                    f"alias '{alias}' already registered by broker '{existing_target}'"
                )
        for alias, target in list(self._broker_alias_map.items()):
            if target == broker and alias not in new_aliases:
                self._broker_alias_map.pop(alias, None)
        self._parser_registry[broker] = CsvParserSpec(
            broker=broker,
            aliases=new_aliases,
            display_name=spec.display_name or broker,
            column_hints=dict(spec.column_hints or {}),
            default_currency=spec.default_currency,
            default_market_suffix=spec.default_market_suffix,
            sample_csv=spec.sample_csv,
        )
        for alias in self._parser_registry[broker].aliases:
            self._broker_alias_map[alias] = broker

    def get_csv_template(self, broker: str) -> Tuple[str, str]:
        """Return ``(filename, csv_text)`` example template for the given broker."""
        broker_norm = self._normalize_broker(broker)
        spec = self._parser_registry[broker_norm]
        csv_text = spec.sample_csv or (
            "Tarih;Kod;İşlem;Adet;Fiyat;Komisyon;Para Birimi;İşlem No\n"
            "20.11.2026;THYAO.IS;AL;10;312,50;0,00;TRY;TR-001\n"
        )
        return f"{broker_norm}_ornek_sablon.csv", csv_text

    def list_supported_brokers(self) -> List[Dict[str, Any]]:
        """List canonical broker ids and aliases for frontend selector."""
        items: List[Dict[str, Any]] = []
        for broker in sorted(self._parser_registry.keys()):
            aliases = sorted(alias for alias, target in self._broker_alias_map.items() if target == broker)
            items.append(
                {
                    "broker": broker,
                    "aliases": aliases,
                    "display_name": self._parser_registry[broker].display_name,
                }
            )
        return items

    def parse_trade_csv(
        self,
        *,
        broker: str,
        content: bytes,
    ) -> Dict[str, Any]:
        broker_norm = self._normalize_broker(broker)
        parser_spec = self._parser_registry[broker_norm]
        df = self._read_csv(content)

        records: List[Dict[str, Any]] = []
        skipped = 0
        errors: List[str] = []

        for idx, row in df.iterrows():
            normalized = self._normalize_trade_row(row=row, parser_spec=parser_spec)
            if normalized is None:
                skipped += 1
                continue
            try:
                # Keep a stable line-level marker so repeated imports of the same
                # file remain idempotent, while identical split fills on separate
                # CSV lines do not collapse into one dedup key.
                normalized["_source_line_number"] = int(idx) + 2
                normalized["dedup_hash"] = self._build_dedup_hash(normalized)
                records.append(normalized)
            except Exception as exc:  # pragma: no cover - defensive path
                skipped += 1
                errors.append(f"row={idx + 1}: {exc}")

        return {
            "broker": broker_norm,
            "record_count": len(records),
            "skipped_count": skipped,
            "error_count": len(errors),
            "records": records,
            "errors": errors[:20],
        }

    def commit_trade_records(
        self,
        *,
        account_id: int,
        broker: str,
        records: List[Dict[str, Any]],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        broker_norm = self._normalize_broker(broker)

        inserted_count = 0
        duplicate_count = 0
        failed_count = 0
        errors: List[str] = []
        seen_trade_uids: set[str] = set()
        seen_dedup_hashes: set[str] = set()

        for i, record in enumerate(records):
            try:
                trade_uid = (record.get("trade_uid") or "").strip() or None
                dedup_hash = (record.get("dedup_hash") or "").strip()
                if not dedup_hash:
                    dedup_hash = self._build_dedup_hash(record)

                if trade_uid and self.repo.has_trade_uid(account_id, trade_uid):
                    duplicate_count += 1
                    continue
                dedup_hash_to_use: Optional[str] = dedup_hash or None
                if dedup_hash_to_use and self.repo.has_trade_dedup_hash(account_id, dedup_hash_to_use):
                    duplicate_count += 1
                    continue

                if dry_run:
                    if trade_uid and trade_uid in seen_trade_uids:
                        duplicate_count += 1
                        continue
                    if dedup_hash_to_use and dedup_hash_to_use in seen_dedup_hashes:
                        duplicate_count += 1
                        continue
                    inserted_count += 1
                    if trade_uid:
                        seen_trade_uids.add(trade_uid)
                    if dedup_hash_to_use:
                        seen_dedup_hashes.add(dedup_hash_to_use)
                    continue

                trade_date_value = record.get("trade_date")
                if isinstance(trade_date_value, date):
                    trade_date_obj = trade_date_value
                else:
                    trade_date_obj = date.fromisoformat(str(trade_date_value))

                self.portfolio_service.record_trade(
                    account_id=account_id,
                    symbol=str(record["symbol"]),
                    trade_date=trade_date_obj,
                    side=str(record["side"]),
                    quantity=float(record["quantity"]),
                    price=float(record["price"]),
                    fee=float(record.get("fee", 0.0) or 0.0),
                    tax=float(record.get("tax", 0.0) or 0.0),
                    market=record.get("market"),
                    currency=record.get("currency"),
                    trade_uid=trade_uid,
                    dedup_hash=dedup_hash_to_use,
                    note=(record.get("note") or "").strip() or f"csv_import:{broker_norm}",
                )
                inserted_count += 1
            except PortfolioConflictError:
                duplicate_count += 1
            except PortfolioOversellError as exc:
                failed_count += 1
                errors.append(f"idx={i}: {exc}")
            except PortfolioBusyError as exc:
                failed_count += 1
                errors.append(f"idx={i}: portfolio_busy: {exc}")
            except Exception as exc:
                failed_count += 1
                errors.append(f"idx={i}: {exc}")

        return {
            "account_id": account_id,
            "record_count": len(records),
            "inserted_count": inserted_count,
            "duplicate_count": duplicate_count,
            "failed_count": failed_count,
            "dry_run": bool(dry_run),
            "errors": errors[:20],
        }

    def _normalize_broker(self, value: str) -> str:
        broker = (value or "").strip().lower()
        broker = self._broker_alias_map.get(broker, broker)
        if broker not in self._parser_registry:
            supported = ", ".join(sorted(self._parser_registry.keys()))
            raise ValueError(f"broker must be one of: {supported}")
        return broker

    @staticmethod
    def _detect_csv_sep(text: str) -> str:
        first_line = text.splitlines()[0] if text else ""
        if first_line.count(";") > first_line.count(","):
            return ";"
        return ","

    @classmethod
    def _read_csv(cls, content: bytes) -> pd.DataFrame:
        if content.lstrip()[:4] == b"PK\x03\x04":
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl", dtype=str)
            return df.fillna("")
        for encoding in ("utf-8-sig", "gbk", "gb18030", "cp1254"):
            try:
                decoded = content.decode(encoding)
                sep = cls._detect_csv_sep(decoded)
                return pd.read_csv(
                    io.StringIO(decoded),
                    sep=sep,
                    dtype=str,
                    keep_default_na=False,
                )
            except UnicodeDecodeError:
                continue
        return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)

    def _normalize_trade_row(
        self,
        *,
        row: Any,
        parser_spec: CsvParserSpec,
    ) -> Optional[Dict[str, Any]]:
        broker_hints = parser_spec.column_hints

        trade_date_raw = self._pick(
            row,
            *(broker_hints.get("trade_date") or ()),
            "成交日期",
            "发生日期",
            "日期",
            "成交时间",
            "İşlem Tarihi",
            "Islem Tarihi",
            "Tarih",
            "Transaction Date",
            "Trade Date",
            "Date(UTC)",
            "Date",
        )
        trade_date_obj = self._parse_date(trade_date_raw)
        if trade_date_obj is None:
            return None

        symbol_raw = self._pick(
            row,
            *(broker_hints.get("symbol") or ()),
            "证券代码",
            "股票代码",
            "代码",
            "Hisse Kodu",
            "Sembol",
            "Kod",
            "Ticker",
            "Symbol",
            "Pair",
            "Market",
        )
        raw_sym_text = str(symbol_raw or "").strip()
        if parser_spec.broker == "binance_spot":
            symbol = raw_sym_text.upper().replace("/", "").replace("-", "").replace(" ", "")
        else:
            symbol = canonical_stock_code(raw_sym_text)
            if (
                parser_spec.default_market_suffix
                and symbol
                and "." not in symbol
                and _TR_TICKER_RE.fullmatch(symbol.upper())
            ):
                symbol = f"{symbol.upper()}{parser_spec.default_market_suffix}"
        if not symbol:
            return None

        side_raw = self._pick(
            row,
            *(broker_hints.get("side") or ()),
            "买卖标志",
            "买卖方向",
            "交易方向",
            "业务名称",
            "操作",
            "İşlem Türü",
            "Islem Turu",
            "Yön",
            "Yon",
            "İşlem",
            "Side",
            "Type",
        )
        side = self._normalize_side(side_raw)
        if side is None:
            return None

        quantity = self._parse_float(
            self._pick(
                row,
                *(broker_hints.get("quantity") or ()),
                "成交数量",
                "数量",
                "成交股数",
                "Adet",
                "Lot",
                "Miktar",
                "Shares",
                "Executed",
                "Quantity",
                "Qty",
            )
        )
        price = self._parse_float(
            self._pick(
                row,
                *(broker_hints.get("price") or ()),
                "成交均价",
                "成交价格",
                "价格",
                "成交价",
                "均价",
                "Birim Fiyat",
                "Fiyat",
                "Execution Price",
                "Price",
            )
        )
        if quantity is None or quantity <= 0 or price is None or price <= 0:
            return None

        fee = 0.0
        for col in ("手续费", "佣金", "交易费", "规费", "过户费", "Komisyon", "İşlem Ücreti", "Fee", "Commission"):
            value = self._parse_float(self._pick(row, col))
            if value is not None:
                fee += abs(value)

        tax = 0.0
        for col in ("印花税", "税费", "其他税费", "BSMV", "Vergi", "Tax"):
            value = self._parse_float(self._pick(row, col))
            if value is not None:
                tax += abs(value)

        trade_uid = self._pick(
            row,
            *(broker_hints.get("trade_uid") or ()),
            "成交编号",
            "成交序号",
            "合同编号",
            "委托编号",
            "流水号",
            "Referans No",
            "Emir No",
            "İşlem No",
            "Order ID",
            "Trade ID",
            "Ref",
        )
        currency = self._pick(row, "币种", "货币", "Para Birimi", "Döviz", "Currency", "Fee Coin")
        currency_norm = (str(currency).strip().upper() if currency is not None else "") or parser_spec.default_currency

        return {
            "trade_date": trade_date_obj,
            "symbol": symbol,
            "side": side,
            "quantity": float(quantity),
            "price": float(price),
            "fee": float(fee),
            "tax": float(tax),
            "trade_uid": (str(trade_uid).strip() if trade_uid is not None else None) or None,
            "currency": currency_norm or None,
        }

    @staticmethod
    def _pick(row: Any, *candidates: str) -> Any:
        for name in candidates:
            if name in row.index:
                value = row.get(name)
                if value is not None and str(value).strip() != "" and str(value).strip().lower() != "nan":
                    return value
        return None

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        sign = -1.0 if text.startswith("-") else 1.0
        match = re.search(r"([0-9][0-9.,]*)", text)
        if not match:
            return None
        num_str = match.group(1)
        if "." in num_str and "," in num_str:
            if num_str.rfind(",") > num_str.rfind("."):
                num_str = num_str.replace(".", "").replace(",", ".")
            else:
                num_str = num_str.replace(",", "")
        elif "," in num_str:
            if re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})+", num_str):
                num_str = num_str.replace(",", "")
            else:
                num_str = num_str.replace(",", ".")
        try:
            return sign * float(num_str)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        dayfirst = bool(re.match(r"^\d{1,2}[./]\d{1,2}[./]\d{2,4}", text))
        parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()

    @staticmethod
    def _normalize_side(value: Any) -> Optional[str]:
        raw = str(value or "").strip()
        if not raw:
            return None
        text = raw.lower()
        compact = text.replace(" ", "")
        buy_exact = {
            "buy",
            "b",
            "al",
            "alış",
            "aliş",
            "alis",
            "alım",
            "alim",
            "hissealış",
            "hissealiş",
            "hissealis",
            "买",
            "买入",
            "证券买入",
            "普通买入",
        }
        sell_exact = {
            "sell",
            "s",
            "sat",
            "satış",
            "satiş",
            "satis",
            "satım",
            "satim",
            "hissesatış",
            "hissesatiş",
            "hissesatis",
            "卖",
            "卖出",
            "证券卖出",
            "普通卖出",
        }
        if compact in buy_exact:
            return "buy"
        if compact in sell_exact:
            return "sell"
        if "买入" in compact or compact.startswith("买"):
            return "buy"
        if "卖出" in compact or compact.startswith("卖"):
            return "sell"
        return None

    @staticmethod
    def _build_dedup_hash(record: Dict[str, Any]) -> str:
        payload = "|".join(
            [
                str(record.get("trade_date") or ""),
                str(record.get("symbol") or ""),
                str(record.get("side") or ""),
                f"{float(record.get('quantity', 0.0)):.8f}",
                f"{float(record.get('price', 0.0)):.8f}",
                f"{float(record.get('fee', 0.0)):.8f}",
                f"{float(record.get('tax', 0.0)):.8f}",
                str(record.get("currency") or ""),
                str(record.get("_source_line_number") or record.get("source_line_number") or ""),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
