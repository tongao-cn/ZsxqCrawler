"""Daily stock and concept extraction for group topics."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
)
from backend.services.daily_stock_concept_sources import resolve_daily_stock_concepts
from backend.services.daily_stock_concept_store import load_daily_stock_concepts, save_daily_stock_concepts
from backend.services.topic_material import (
    DEFAULT_COMMENTS_PER_TOPIC,
    connect_topic_material_db,
    load_daily_topic_material,
    parse_topic_material_date,
)


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback:
        log_callback(message)


def extract_daily_stock_concepts(
    group_id: str,
    report_date: Optional[str] = None,
    *,
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    parsed_date = parse_topic_material_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = connect_topic_material_db(group_id)

    try:
        _log(log_callback, f"📚 读取 {report_date_text} 的话题数据...")
        material = load_daily_topic_material(
            group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        _log(log_callback, f"📊 当天话题数量: {material.topic_count}")
        if material.topic_count == 0:
            stocks: List[Dict[str, Any]] = []
            model = ""
        else:
            resolution = resolve_daily_stock_concepts(
                group_id=group_id,
                report_date=report_date_text,
                prompt_payload=material.prompt_payload,
                log_callback=log_callback,
            )
            stocks = resolution.stocks
            model = resolution.model

        save_daily_stock_concepts(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            stocks=stocks,
            model=model,
            status="completed",
        )
        _log(log_callback, f"✅ 股票概念提取完成，共 {len(stocks)} 条")
        return {
            "group_id": group_id,
            "report_date": report_date_text,
            "stocks": stocks,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    except Exception as exc:
        save_daily_stock_concepts(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            stocks=[],
            model=str(get_openai_compatible_config().get("model") or ""),
            status="failed",
            error=str(exc),
        )
        raise
    finally:
        conn.close()


def get_daily_stock_concepts(group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    parsed_date = parse_topic_material_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = connect_topic_material_db(group_id)
    try:
        return load_daily_stock_concepts(conn, group_id=group_id, report_date=report_date_text)
    finally:
        conn.close()


__all__ = [
    "extract_daily_stock_concepts",
    "get_daily_stock_concepts",
]
