from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.ai_json_utils import extract_json_object
from backend.services.a_share_analysis_db_storage import load_stock_basic_records
from backend.services.stock_concept_taxonomy import normalize_stock_concept_term


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_stock_name(value: Any) -> str:
    name = _normalize_text(value)
    for suffix in ("股份有限公司", "有限责任公司", "集团股份", "集团"):
        name = name.replace(suffix, "")
    return name.strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.0, min(1.0, parsed))


def _safe_string_list(value: Any, *, limit: int = 12) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned: List[str] = []
    seen = set()
    for item in value:
        text = _normalize_text(item)
        if not text or text in seen:
            continue
        cleaned.append(text[:80])
        seen.add(text)
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
        name = _normalize_text(record.get("name"))
        if not name:
            continue
        normalized = _normalize_stock_name(name)
        stock_info = {
            "stock_name": name,
            "stock_code": _symbol_from_ts_code(record.get("ts_code", "")) or _normalize_text(record.get("symbol")),
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


def _match_stock(stock_name: str, lookup: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    name = _normalize_stock_name(stock_name)
    if not name:
        return None
    return lookup.get(stock_name) or lookup.get(name)


def parse_stock_concept_output(
    message: str,
    *,
    stock_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    payload = extract_json_object(message)
    return parse_stock_concept_payload(payload, stock_lookup=stock_lookup)


def parse_stock_concept_payload(
    payload: Dict[str, Any],
    *,
    stock_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    raw_stocks = payload.get("stocks")
    if not isinstance(raw_stocks, list):
        return []

    lookup = stock_lookup if stock_lookup is not None else build_stock_lookup()
    results: List[Dict[str, Any]] = []
    seen = set()
    for raw in raw_stocks:
        if not isinstance(raw, dict):
            continue
        stock_name = _normalize_stock_name(raw.get("stock_name"))
        if not stock_name or stock_name in seen:
            continue
        matched = _match_stock(stock_name, lookup)
        stock_code = _normalize_text(raw.get("stock_code"))
        market = _normalize_text(raw.get("market")).upper()
        confidence = _safe_float(raw.get("confidence"))
        if matched:
            stock_name = matched["stock_name"] or stock_name
            stock_code = matched["stock_code"] or stock_code
            market = matched["market"] or market
            confidence = max(confidence, 0.7)
        elif not stock_code:
            confidence = min(confidence, 0.5)

        concepts = _safe_string_list(raw.get("concepts"), limit=10)
        topic_ids = _safe_string_list(raw.get("topic_ids"), limit=50)
        results.append(
            {
                "stock_name": stock_name,
                "stock_code": stock_code,
                "market": market,
                "concepts": concepts,
                "reason": _normalize_text(raw.get("reason"))[:1000],
                "topic_ids": topic_ids,
                "confidence": confidence,
            }
        )
        seen.add(stock_name)
    return results


def aggregate_topic_stock_extractions(
    rows: List[Dict[str, Any]],
    *,
    stock_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []

    lookup = stock_lookup if stock_lookup is not None else build_stock_lookup()
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        stock_name = _normalize_stock_name(row.get("stock_name"))
        if not stock_name:
            continue
        key = stock_name
        item = grouped.setdefault(
            key,
            {
                "stock_name": stock_name,
                "stock_code": _normalize_text(row.get("stock_code")),
                "market": _normalize_text(row.get("market")).upper(),
                "concepts": [],
                "reason_parts": [],
                "topic_ids": set(),
                "confidence_values": [],
            },
        )
        for concept in _safe_string_list(row.get("concepts"), limit=10):
            class_name, normalized = normalize_stock_concept_term(concept)
            if class_name == "empty" or not normalized:
                continue
            if normalized not in item["concepts"]:
                item["concepts"].append(normalized)
        reason = _normalize_text(row.get("reason"))
        topic_id = _normalize_text(row.get("topic_id"))
        if reason and reason not in item["reason_parts"]:
            item["reason_parts"].append(reason)
        if topic_id:
            item["topic_ids"].add(topic_id)
        item["confidence_values"].append(_safe_float(row.get("confidence")))

    results: List[Dict[str, Any]] = []
    for item in grouped.values():
        matched = _match_stock(item["stock_name"], lookup)
        stock_name = item["stock_name"]
        stock_code = item["stock_code"]
        market = item["market"]
        confidence_values = [value for value in item["confidence_values"] if value > 0]
        confidence = max(confidence_values) if confidence_values else 0.0
        if matched:
            stock_name = matched["stock_name"] or stock_name
            stock_code = matched["stock_code"] or stock_code
            market = matched["market"] or market
            confidence = max(confidence, 0.7)
        elif not stock_code:
            confidence = min(confidence, 0.5)
        reason = "；".join(item["reason_parts"])[:1000]
        results.append(
            {
                "stock_name": stock_name,
                "stock_code": stock_code,
                "market": market,
                "concepts": item["concepts"][:10],
                "reason": reason,
                "topic_ids": sorted(item["topic_ids"]),
                "confidence": confidence,
            }
        )

    return sorted(results, key=lambda item: (-float(item.get("confidence") or 0), str(item.get("stock_name") or "")))
