"""Pure helpers for stock topic analysis."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_company_name(value: Any) -> str:
    return (
        _normalize_text(value)
        .replace(" ", "")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
    )


def _parse_json_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [_normalize_text(item) for item in parsed if _normalize_text(item)]


def _ordered_unique(values: Iterable[Any], *, limit: int = 50) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _build_stock_alias_terms(stock_name: Any, stock_code: Any = "", market: Any = "") -> List[str]:
    name = _normalize_text(stock_name)
    normalized_name = _normalize_company_name(name)
    code = _normalize_text(stock_code)
    market_text = _normalize_text(market)
    terms = [name, normalized_name, code]
    if market_text and code:
        terms.extend([f"{market_text}.{code}", f"{market_text}{code}"])
    return _ordered_unique((term for term in terms if term), limit=10)


def _serialize_json_list(values: Iterable[Any], *, limit: int = 5000) -> str:
    return json.dumps(_ordered_unique(values, limit=limit), ensure_ascii=False)


def _topic_ids_from_result(result: Dict[str, Any], *, limit: int = 5000) -> List[str]:
    return _ordered_unique((topic.get("topic_id") for topic in result.get("topics", [])), limit=limit)


def _merge_topic_ids(*groups: Iterable[Any], limit: int = 5000) -> List[str]:
    merged: List[Any] = []
    for group in groups:
        merged.extend(list(group or []))
    return _ordered_unique(merged, limit=limit)


def _topic_id_set(values: Iterable[Any], *, limit: int = 5000) -> set[str]:
    return {str(value) for value in _ordered_unique(values, limit=limit)}


def _exclude_topic_ids(values: Iterable[Any], excluded: Iterable[Any], *, limit: int = 5000) -> List[str]:
    excluded_set = _topic_id_set(excluded, limit=limit)
    return _ordered_unique((value for value in values if str(value) not in excluded_set), limit=limit)


def _chunks(values: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
