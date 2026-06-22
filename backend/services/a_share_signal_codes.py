"""A-share signal stock code resolution."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def company_key(value: Any) -> str:
    key = (
        _normalize_text(value)
        .replace(" ", "")
        .replace("　", "")
        .replace("*", "")
        .replace("－", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
    )
    for suffix in ("-UW", "-U", "-W", "-B"):
        if key.upper().endswith(suffix):
            key = key[: -len(suffix)]
            break
    for prefix in ("DR", "XD", "XR", "ST"):
        if key.upper().startswith(prefix) and len(key) > len(prefix):
            key = key[len(prefix) :]
            break
    return key


def build_stock_basic_index(rows: Iterable[Iterable[Any]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    duplicates = set()
    for ts_code, symbol, name in rows:
        normalized_ts_code = _normalize_text(ts_code).upper()
        if not normalized_ts_code:
            continue
        keys = {company_key(name), _normalize_text(symbol)}
        for key in keys:
            if not key:
                continue
            if key in lookup and lookup[key] != normalized_ts_code:
                duplicates.add(key)
                continue
            lookup[key] = normalized_ts_code
    for key in duplicates:
        lookup.pop(key, None)
    return lookup


def infer_market_from_symbol(symbol: str) -> str:
    if symbol.startswith("6"):
        return "SH"
    if symbol.startswith(("0", "3")):
        return "SZ"
    if symbol.startswith(("4", "8", "9")):
        return "BJ"
    return ""


def resolve_signal_ts_code(signal: Mapping[str, Any], stock_basic_index: Mapping[str, str] | None = None) -> str:
    raw_ts_code = _normalize_text(signal.get("ts_code")).upper()
    if "." in raw_ts_code:
        return raw_ts_code

    stock_code = _normalize_text(signal.get("stock_code") or signal.get("symbol")).upper()
    if "." in stock_code:
        return stock_code
    market = _normalize_text(signal.get("market")).upper()
    if stock_code and not market:
        market = infer_market_from_symbol(stock_code)
    if stock_code and market:
        return f"{stock_code}.{market}"

    lookup = stock_basic_index or {}
    return lookup.get(company_key(signal.get("stock_name")), "")
