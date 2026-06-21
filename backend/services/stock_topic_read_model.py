from __future__ import annotations

from typing import Any, Dict, Iterable, List

from backend.services.stock_topic_analysis_helpers import parse_stock_names
from backend.services.stock_topic_analysis_service import (
    get_latest_stock_topic_analyses,
    search_stock_topics,
)


def _stock_topic_key(result: Dict[str, Any]) -> str:
    return str(result.get("stock_name") or "").strip()


def _ordered_topic_ids(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = "" if value is None else str(value).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _topic_ids_from_latest(latest_result: Dict[str, Any] | None) -> List[str]:
    if not latest_result:
        return []
    return _ordered_topic_ids(latest_result.get("processed_topic_ids") or latest_result.get("analyzed_topic_ids") or [])


def merge_stock_topic_read_model(
    search_result: Dict[str, Any],
    latest_result: Dict[str, Any] | None,
) -> Dict[str, Any]:
    latest_topic_ids = _topic_ids_from_latest(latest_result)
    latest_topic_id_set = set(latest_topic_ids)
    new_topic_count = sum(
        1
        for topic in search_result.get("topics") or []
        if str(topic.get("topic_id")) not in latest_topic_id_set
    )

    if not latest_result or latest_result.get("status") == "missing":
        return {
            **search_result,
            "processed_topic_ids": [],
            "analyzed_topic_ids": [],
            "new_topic_count": search_result.get("topic_count", 0),
            "analysis_mode": "initialize",
        }

    return {
        **search_result,
        "concepts": latest_result.get("concepts") or search_result.get("concepts") or [],
        "recommendation_count": latest_result.get("recommendation_count") or search_result.get("recommendation_count", 0),
        "summary_markdown": latest_result.get("summary_markdown"),
        "model": latest_result.get("model"),
        "status": latest_result.get("status"),
        "error": latest_result.get("error"),
        "created_at": latest_result.get("created_at"),
        "updated_at": latest_result.get("updated_at"),
        "processed_topic_ids": latest_topic_ids,
        "analyzed_topic_ids": latest_topic_ids,
        "new_topic_count": new_topic_count,
        "analysis_mode": "incremental" if new_topic_count > 0 else "up_to_date",
    }


def get_stock_topic_read_models(group_id: str, stock_names: Any) -> List[Dict[str, Any]]:
    names = parse_stock_names(stock_names)
    if not names:
        raise ValueError("stock_names 不能为空")

    group_id_text = str(group_id or "").strip()
    latest_batch = get_latest_stock_topic_analyses(group_id_text, names)
    latest_rows = list(latest_batch.get("stocks") or [])
    latest_by_name = {_stock_topic_key(item): item for item in latest_rows}

    read_models: List[Dict[str, Any]] = []
    for index, stock_name in enumerate(names):
        search_result = search_stock_topics(group_id_text, stock_name)
        latest_result = (
            latest_rows[index]
            if index < len(latest_rows)
            else latest_by_name.get(_stock_topic_key(search_result)) or latest_by_name.get(stock_name)
        )
        read_models.append(merge_stock_topic_read_model(search_result, latest_result))
    return read_models
