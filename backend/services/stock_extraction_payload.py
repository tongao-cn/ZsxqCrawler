from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.a_share_analysis_db_storage import load_stock_basic_records


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_stock_name(value: Any) -> str:
    name = normalize_text(value)
    for suffix in ("股份有限公司", "有限责任公司", "集团股份", "集团"):
        name = name.replace(suffix, "")
    return name.strip()


def safe_confidence(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.0, min(1.0, parsed))


def safe_text_list(
    value: Any,
    *,
    limit: int = 12,
    text_limit: int = 80,
    dedupe_after_truncate: bool = False,
) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned: List[str] = []
    seen = set()
    for item in value:
        text = normalize_text(item)
        rendered = text[:text_limit]
        seen_key = rendered if dedupe_after_truncate else text
        if not rendered or seen_key in seen:
            continue
        cleaned.append(rendered)
        seen.add(seen_key)
        if len(cleaned) >= limit:
            break
    return cleaned


def _market_from_ts_code(ts_code: str) -> str:
    code = str(ts_code or "").strip().upper()
    if code.endswith(".SZ"):
        return "SZ"
    if code.endswith(".SH"):
        return "SH"
    if code.endswith(".BJ"):
        return "BJ"
    return ""


def _symbol_from_ts_code(ts_code: str) -> str:
    return str(ts_code or "").split(".", 1)[0].strip()


def build_stock_lookup(records: Optional[List[Dict[str, str]]] = None) -> Dict[str, Dict[str, str]]:
    try:
        stock_records = records if records is not None else load_stock_basic_records()
    except Exception:
        stock_records = []

    lookup: Dict[str, Dict[str, str]] = {}
    duplicates = set()
    for record in stock_records:
        name = normalize_text(record.get("name"))
        if not name:
            continue
        normalized = normalize_stock_name(name)
        stock_info = {
            "stock_name": name,
            "stock_code": _symbol_from_ts_code(record.get("ts_code", "")) or normalize_text(record.get("symbol")),
            "market": _market_from_ts_code(record.get("ts_code", "")),
        }
        for key in {name, normalized}:
            if not key:
                continue
            if key in lookup:
                duplicates.add(key)
                continue
            lookup[key] = stock_info
    for key in duplicates:
        lookup.pop(key, None)
    return lookup


def match_stock(stock_name: str, lookup: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    name = normalize_stock_name(stock_name)
    if not name:
        return None
    return lookup.get(stock_name) or lookup.get(name)
