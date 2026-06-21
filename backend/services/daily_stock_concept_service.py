"""Daily stock and concept extraction for group topics."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.ai_provider_config import (
    get_extraction_reasoning_effort,
    get_openai_compatible_config,
)
from backend.services.ai_runtime_request import call_structured_ai_object
from backend.services.a_share_analysis_db_storage import load_topic_stock_extractions
from backend.services.daily_stock_concept_payload import (
    aggregate_topic_stock_extractions,
    parse_stock_concept_payload,
)
from backend.services.topic_material import (
    DEFAULT_COMMENTS_PER_TOPIC,
    connect_topic_material_db,
    load_daily_topic_material,
    parse_topic_material_date,
)


STOCK_CONCEPT_PROMPT_VERSION = "daily-stock-concepts-v1"
STOCK_CONCEPT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string"},
                    "stock_code": {"type": "string"},
                    "market": {"type": "string"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "topic_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "stock_name",
                    "stock_code",
                    "market",
                    "concepts",
                    "reason",
                    "topic_ids",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stocks"],
    "additionalProperties": False,
}


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback:
        log_callback(message)


def _generate_stock_concepts_with_ai(prompt_payload: str, report_date: str) -> Tuple[List[Dict[str, Any]], str]:
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股股票和投资概念提取助手。"
                "只基于用户提供的知识星球话题数据提取，不要编造未出现的信息。"
                "如果无法判断为A股上市公司，就不要输出。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请从 {report_date} 的话题数据中提取明确提到的A股股票及对应概念。\n"
                "要求：\n"
                "1. 只输出明确提到或可从上下文明确映射到A股上市公司的股票。\n"
                "2. 概念必须来自上下文，例如固态电池、机器人、算力、低空经济等。\n"
                "3. topic_ids 使用输入中的 topic_id，方便回溯。\n"
                "4. 不确定时降低 confidence；不要猜股票代码。\n"
                "5. 输出必须符合 JSON schema。\n\n"
                f"话题数据：\n{prompt_payload}"
            ),
        },
    ]

    result = call_structured_ai_object(
        messages=messages,
        get_ai_config=get_openai_compatible_config,
        schema_name="daily_stock_concepts",
        schema=STOCK_CONCEPT_SCHEMA,
        label="AI 股票概念抽取结果",
        reasoning_effort=get_extraction_reasoning_effort(),
        timeout=180,
    )

    stocks = parse_stock_concept_payload(result.payload)
    return stocks, result.model


def _delete_stock_concepts(conn: Any, group_id: str, report_date: str) -> None:
    conn.execute(
        "DELETE FROM daily_stock_concepts WHERE group_id = ? AND report_date = ?",
        (group_id, report_date),
    )


def _insert_stock_concepts(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    stocks: List[Dict[str, Any]],
    model: str,
    status: str,
    error: str = "",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    if not stocks:
        conn.execute(
            """
            INSERT INTO daily_stock_concepts (
                group_id, report_date, stock_name, stock_code, market,
                concepts_json, reason, topic_ids_json, confidence,
                model, status, error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, report_date, "", "", "", "[]", error, "[]", 0, model, status, error, now, now),
        )
        return

    for stock in stocks:
        conn.execute(
            """
            INSERT INTO daily_stock_concepts (
                group_id, report_date, stock_name, stock_code, market,
                concepts_json, reason, topic_ids_json, confidence,
                model, status, error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_id,
                report_date,
                stock["stock_name"],
                stock.get("stock_code", ""),
                stock.get("market", ""),
                json.dumps(stock.get("concepts", []), ensure_ascii=False),
                stock.get("reason", ""),
                json.dumps(stock.get("topic_ids", []), ensure_ascii=False),
                stock.get("confidence", 0),
                model,
                status,
                error,
                now,
                now,
            ),
        )


def _save_stock_concepts(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    stocks: List[Dict[str, Any]],
    model: str,
    status: str,
    error: str = "",
) -> None:
    _delete_stock_concepts(conn, group_id, report_date)
    _insert_stock_concepts(
        conn,
        group_id=group_id,
        report_date=report_date,
        stocks=stocks,
        model=model,
        status=status,
        error=error,
    )
    conn.commit()


def _parse_json_list(value: Any) -> List[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


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
            try:
                topic_extractions = load_topic_stock_extractions(
                    group_id=group_id,
                    start_date=report_date_text,
                    end_date=report_date_text,
                )
            except Exception as exc:
                topic_extractions = []
                _log(log_callback, f"⚠️ 读取话题级A股明细失败，将回退按天 AI 提取: {exc}")
            if topic_extractions:
                _log(log_callback, f"🧩 使用话题级A股抽取明细聚合股票概念: {len(topic_extractions)} 条")
                stocks = aggregate_topic_stock_extractions(topic_extractions)
                model_values = [str(item.get("model") or "") for item in topic_extractions if item.get("model")]
                model = model_values[0] if model_values else ""
            else:
                _log(log_callback, "🤖 未找到话题级明细，回退为按天 AI 提取股票概念...")
                stocks, model = _generate_stock_concepts_with_ai(material.prompt_payload, report_date_text)

        _save_stock_concepts(
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
        _save_stock_concepts(
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
        rows = conn.execute(
            """
            SELECT stock_name, stock_code, market, concepts_json, reason,
                   topic_ids_json, confidence, model, status, error, updated_at
            FROM daily_stock_concepts
            WHERE group_id = ? AND report_date = ?
            ORDER BY confidence DESC, stock_name ASC
            """,
            (group_id, report_date_text),
        ).fetchall()
        if not rows:
            return None

        first = rows[0]
        status = first["status"]
        error = first["error"]
        stocks = []
        for row in rows:
            if not row["stock_name"]:
                continue
            stocks.append(
                {
                    "stock_name": row["stock_name"],
                    "stock_code": row["stock_code"] or "",
                    "market": row["market"] or "",
                    "concepts": _parse_json_list(row["concepts_json"]),
                    "reason": row["reason"] or "",
                    "topic_ids": _parse_json_list(row["topic_ids_json"]),
                    "confidence": float(row["confidence"] or 0),
                    "model": row["model"] or "",
                }
            )
        return {
            "group_id": group_id,
            "report_date": report_date_text,
            "stocks": stocks,
            "status": status,
            "error": error,
            "updated_at": first["updated_at"],
        }
    finally:
        conn.close()


__all__ = [
    "extract_daily_stock_concepts",
    "get_daily_stock_concepts",
]
