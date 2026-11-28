# -*- coding: utf-8 -*-
"""Helpers for parsing report sniper-point price values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, Optional


SNIPER_KEYS = ("ideal_buy", "secondary_buy", "stop_loss", "take_profit")


_NUMERIC_TOKEN_RE = re.compile(r"\d[\d.,]*")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_PCT_TOKEN_RE = re.compile(r"(?:%\s*-?\d+(?:\.\d+)?|-?\d+(?:\.\d+)?\s*%)")
_MA_PREFIX_RE = re.compile(r"\b(?:E?MA|RSI|KDJ|MACD)\s*\d+\b", re.IGNORECASE)
_CURRENCY_PRICE_RE = re.compile(
    r"(?:[$₺€]\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:TL|TRY|USD|EUR|dolar)\b)",
    re.IGNORECASE,
)


def _normalize_numeric_token(token: str) -> str:
    """Normalize US thousands vs Turkish/European decimal commas in a numeric token."""
    if "," not in token:
        return token
    if "." in token:
        last_dot = token.rfind(".")
        last_comma = token.rfind(",")
        if last_comma > last_dot and len(token[last_comma + 1:]) != 3:
            # e.g. "1.234,56" -> "1234.56"
            return token.replace(".", "").replace(",", ".")
        if last_comma > last_dot and re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+", token):
            # e.g. "1.234,560" -> "1234.560"
            return token.replace(".", "").replace(",", ".")
        # e.g. "1,234.56" -> "1234.56"
        return token.replace(",", "")

    if token.count(",") > 1:
        # e.g. "1,234,567" -> "1234567"
        return token.replace(",", "")

    int_part, frac_part = token.split(",", 1)
    if not frac_part:
        return int_part
    # Turkish/European decimal comma ("152,28", "33,00", "0,825", "3,5") vs English thousands ("1,250").
    if len(frac_part) != 3 or int_part == "0":
        return f"{int_part}.{frac_part}"
    return f"{int_part}{frac_part}"


def _normalize_localized_separators(raw_text: str) -> str:
    text = raw_text.replace("，", " ").strip()
    return _NUMERIC_TOKEN_RE.sub(lambda m: _normalize_numeric_token(m.group(0)), text)


def parse_sniper_value(value: Any) -> Optional[float]:
    """Parse a sniper point value from report text into a positive price."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed > 0 else None

    text = _normalize_localized_separators(str(value))
    if not text or text in {"-", "—", "N/A"}:
        return None

    try:
        parsed = float(text)
        return parsed if parsed > 0 else None
    except ValueError:
        pass

    colon_pos = max(text.rfind("："), text.rfind(":"))
    yuan_pos = text.find("元", colon_pos + 1 if colon_pos != -1 else 0)
    if yuan_pos != -1:
        segment_start = colon_pos + 1 if colon_pos != -1 else 0
        segment = text[segment_start:yuan_pos]
        valid_numbers = []
        for match in re.finditer(r"-?\d+(?:\.\d+)?", segment):
            start_idx = match.start()
            if start_idx >= 2 and segment[start_idx - 2:start_idx].upper() == "MA":
                continue
            valid_numbers.append(match.group())
        if valid_numbers:
            try:
                parsed = abs(float(valid_numbers[-1]))
                return parsed if parsed > 0 else None
            except ValueError:
                pass

    paren_pos = len(text)
    for paren_char in ("(", "（"):
        pos = text.find(paren_char)
        if pos != -1:
            paren_pos = min(paren_pos, pos)
    search_text = text[:paren_pos].strip() or text

    # Strip non-price numeric noise (ISO dates like 2026-11-23, %0.6 / 2%, MA5/EMA20).
    cleaned_text = _ISO_DATE_RE.sub(" ", search_text)
    cleaned_text = _PCT_TOKEN_RE.sub(" ", cleaned_text)
    cleaned_text = _MA_PREFIX_RE.sub(" ", cleaned_text)

    # Prefer the stated price tagged with a currency in the leading clause (before ";"),
    # avoiding dates, percentages, or secondary reference numbers in trailing notes.
    primary_clause = cleaned_text.split(";", 1)[0].strip() or cleaned_text
    currency_match = _CURRENCY_PRICE_RE.search(primary_clause)
    if currency_match:
        num_str = currency_match.group(1) or currency_match.group(2)
        try:
            parsed = float(num_str)
            return parsed if parsed > 0 else None
        except ValueError:
            pass

    valid_numbers = []
    for match in re.finditer(r"\d+(?:\.\d+)?", primary_clause):
        start_idx = match.start()
        if start_idx >= 2 and primary_clause[start_idx - 2:start_idx].upper() == "MA":
            continue
        valid_numbers.append(match.group())
    if not valid_numbers and primary_clause != cleaned_text:
        for match in re.finditer(r"\d+(?:\.\d+)?", cleaned_text):
            start_idx = match.start()
            if start_idx >= 2 and cleaned_text[start_idx - 2:start_idx].upper() == "MA":
                continue
            valid_numbers.append(match.group())
    if valid_numbers:
        try:
            parsed = float(valid_numbers[-1])
            return parsed if parsed > 0 else None
        except ValueError:
            pass
    return None


def extract_sniper_points(result: Any) -> Dict[str, Optional[float]]:
    """Extract normalized sniper-point prices from a completed analysis result."""

    raw_points: Mapping[str, Any] = {}

    if hasattr(result, "get_sniper_points"):
        candidate = result.get_sniper_points() or {}
        if isinstance(candidate, Mapping):
            raw_points = candidate

    if not _has_any_sniper_value(raw_points):
        dashboard = getattr(result, "dashboard", None)
        if isinstance(dashboard, Mapping):
            raw_points = find_sniper_points(dashboard) or raw_points

    if not _has_any_sniper_value(raw_points):
        raw_response = getattr(result, "raw_response", None)
        if isinstance(raw_response, Mapping):
            raw_points = find_sniper_points(raw_response) or raw_points

    return {key: parse_sniper_value(raw_points.get(key)) for key in SNIPER_KEYS}


def _has_any_sniper_value(points: Mapping[str, Any]) -> bool:
    return any(points.get(key) not in (None, "") for key in SNIPER_KEYS)


def find_sniper_points(data: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    if not isinstance(data, Mapping):
        return None

    if any(key in data for key in SNIPER_KEYS):
        return data

    sniper_points = data.get("sniper_points")
    if isinstance(sniper_points, Mapping) and sniper_points:
        return sniper_points

    battle_plan = data.get("battle_plan")
    if isinstance(battle_plan, Mapping):
        sniper_points = battle_plan.get("sniper_points")
        if isinstance(sniper_points, Mapping) and sniper_points:
            return sniper_points

    inner_dashboard = data.get("dashboard")
    if isinstance(inner_dashboard, Mapping):
        found = find_sniper_points(inner_dashboard)
        if found:
            return found

    return None
