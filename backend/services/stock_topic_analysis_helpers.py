"""Pure helpers for stock topic analysis."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional


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


def _reconcile_processed_topic_ids(latest: Dict[str, Any] | None, search_result: Dict[str, Any]) -> Dict[str, Any]:
    saved_topic_ids = list((latest or {}).get("processed_topic_ids") or (latest or {}).get("analyzed_topic_ids") or [])
    current_topic_ids = _topic_ids_from_result(search_result)
    saved_topic_id_set = _topic_id_set(saved_topic_ids)
    new_topic_ids = [topic_id for topic_id in current_topic_ids if topic_id not in saved_topic_id_set]
    new_skipped_topic_ids = _exclude_topic_ids(search_result.get("skipped_topic_ids") or [], saved_topic_ids)
    processed_topic_ids = _merge_topic_ids(saved_topic_ids, search_result.get("processed_topic_ids") or [], new_skipped_topic_ids)
    has_new_processed_topic_ids = len(_topic_id_set(processed_topic_ids)) > len(saved_topic_id_set)
    return {
        "saved_topic_ids": saved_topic_ids,
        "current_topic_ids": current_topic_ids,
        "new_topic_ids": new_topic_ids,
        "new_skipped_topic_ids": new_skipped_topic_ids,
        "processed_topic_ids": processed_topic_ids,
        "has_new_processed_topic_ids": has_new_processed_topic_ids,
    }


def _build_saved_stock_analysis_result(
    search_result: Dict[str, Any],
    latest: Dict[str, Any],
    *,
    processed_topic_ids: Iterable[Any],
    analyzed_topic_ids: Iterable[Any],
) -> Dict[str, Any]:
    return {
        **search_result,
        "summary_markdown": latest.get("summary_markdown", ""),
        "model": latest.get("model", ""),
        "status": latest.get("status", "completed"),
        "error": latest.get("error", ""),
        "created_at": latest.get("created_at"),
        "updated_at": latest.get("updated_at"),
        "processed_topic_ids": list(processed_topic_ids),
        "analyzed_topic_ids": list(analyzed_topic_ids),
        "new_topic_count": 0,
        "analysis_mode": "up_to_date",
    }


def _build_stock_analysis_result(
    search_result: Dict[str, Any],
    *,
    summary_markdown: str,
    model: str,
    processed_topic_ids: Iterable[Any],
    analyzed_topic_ids: Optional[Iterable[Any]] = None,
    new_topic_count: int,
    analysis_mode: str,
    status: Optional[str] = "completed",
    topics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    result = {
        **search_result,
        "summary_markdown": summary_markdown,
        "model": model,
        "processed_topic_ids": list(processed_topic_ids),
        "analyzed_topic_ids": list(analyzed_topic_ids if analyzed_topic_ids is not None else processed_topic_ids),
        "new_topic_count": new_topic_count,
        "analysis_mode": analysis_mode,
    }
    if status is not None:
        result["status"] = status
    if topics is not None:
        result["topics"] = topics
    return result


def _chunks(values: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
