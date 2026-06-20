"""Daily stock and concept extraction for group topics."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_extraction_reasoning_effort,
    get_openai_compatible_config,
)
from backend.services.ai_client import (
    AITextRequest,
    call_ai_text,
    chat_json_schema_response_format,
    responses_json_schema_text_format,
)
from backend.services.ai_json_utils import extract_json_object
from backend.services.a_share_analysis_db_storage import load_stock_basic_records, load_topic_stock_extractions
from backend.services.daily_topic_analysis_service import (
    DEFAULT_COMMENTS_PER_TOPIC,
    _build_prompt_payload,
    _connect_topics_db,
    _fetch_topics_for_date,
    _parse_report_date,
)
from backend.services.stock_concept_taxonomy import normalize_stock_concept_term


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


def _extract_json_object(text: str) -> Dict[str, Any]:
    return extract_json_object(text)


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


def _build_stock_lookup(records: Optional[List[Dict[str, str]]] = None) -> Dict[str, Dict[str, str]]:
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


def _parse_stock_concept_output(
    message: str,
    *,
    stock_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    payload = _extract_json_object(message)
    raw_stocks = payload.get("stocks")
    if not isinstance(raw_stocks, list):
        return []

    lookup = stock_lookup if stock_lookup is not None else _build_stock_lookup()
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


def _aggregate_topic_stock_extractions(
    rows: List[Dict[str, Any]],
    *,
    stock_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []

    lookup = stock_lookup if stock_lookup is not None else _build_stock_lookup()
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


def _get_responses_json_schema_text_format() -> Dict[str, Any]:
    return responses_json_schema_text_format("daily_stock_concepts", STOCK_CONCEPT_SCHEMA)


def _get_chat_json_schema_response_format() -> Dict[str, Any]:
    return chat_json_schema_response_format("daily_stock_concepts", STOCK_CONCEPT_SCHEMA)


def _generate_stock_concepts_with_ai(prompt_payload: str, report_date: str) -> Tuple[List[Dict[str, Any]], str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = str(runtime_ai_config.get("model") or get_default_model())
    api_base = str(runtime_ai_config.get("base_url") or get_default_base_url())
    wire_api = str(runtime_ai_config.get("wire_api") or get_default_wire_api())
    reasoning_effort = get_extraction_reasoning_effort()

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

    message = call_ai_text(
        AITextRequest(
            api_key=api_key,
            model=model,
            api_base=api_base,
            messages=messages,
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            timeout=180,
            responses_text_format=_get_responses_json_schema_text_format(),
            chat_response_format=_get_chat_json_schema_response_format(),
        )
    )

    stocks = _parse_stock_concept_output(message)
    return stocks, model


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
    parsed_date = _parse_report_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = _connect_topics_db(group_id)

    try:
        _log(log_callback, f"📚 读取 {report_date_text} 的话题数据...")
        topics = _fetch_topics_for_date(
            conn,
            group_id=group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        _log(log_callback, f"📊 当天话题数量: {len(topics)}")
        if not topics:
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
                stocks = _aggregate_topic_stock_extractions(topic_extractions)
                model_values = [str(item.get("model") or "") for item in topic_extractions if item.get("model")]
                model = model_values[0] if model_values else ""
            else:
                prompt_payload = _build_prompt_payload(group_id, report_date_text, topics)
                _log(log_callback, "🤖 未找到话题级明细，回退为按天 AI 提取股票概念...")
                stocks, model = _generate_stock_concepts_with_ai(prompt_payload, report_date_text)

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
    parsed_date = _parse_report_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = _connect_topics_db(group_id)
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
    "_aggregate_topic_stock_extractions",
    "_build_stock_lookup",
    "_parse_stock_concept_output",
]
