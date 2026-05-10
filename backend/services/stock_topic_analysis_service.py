"""Stock-scoped topic search and AI summary for a group."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, List, Tuple

from openai import OpenAI

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.daily_topic_analysis_service import _clip, _extract_response_text
from backend.storage.db_compat import connect


MAX_MATCHED_TOPICS = 80
MAX_ANALYSIS_TOPICS = 30
MAX_TOPIC_TEXT_CHARS = 1800
MAX_ANALYSIS_PROMPT_CHARS = 50000
STOCK_TOPIC_ANALYSIS_TABLE = "stock_topic_analyses"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _log(log_callback: Callable[[str], None] | None, message: str) -> None:
    if log_callback:
        log_callback(message)


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


def _topic_content(row: Any) -> str:
    return "\n".join(
        part
        for part in (
            _normalize_text(row["title"]),
            _normalize_text(row["talk_text"]),
            _normalize_text(row["question_text"]),
            _normalize_text(row["answer_text"]),
        )
        if part
    )


def _empty_search_result(group_id: str, stock_name: str) -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "stock_name": stock_name,
        "stock_code": "",
        "market": "",
        "topics": [],
        "concepts": [],
        "topic_count": 0,
        "recommendation_count": 0,
    }


def _serialize_json_list(values: Iterable[Any]) -> str:
    return json.dumps(_ordered_unique(values, limit=200), ensure_ascii=False)


def _build_topic_search_sql() -> str:
    return """
        SELECT
            t.topic_id,
            t.title,
            t.create_time,
            t.likes_count,
            t.comments_count,
            t.reading_count,
            tk.text AS talk_text,
            q.text AS question_text,
            a.text AS answer_text,
            e.stock_name,
            e.stock_code,
            e.market,
            e.concepts_json,
            e.reason,
            e.confidence,
            e.topic_date::text AS topic_date
        FROM topics t
        LEFT JOIN talks tk ON t.topic_id = tk.topic_id
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        LEFT JOIN zsxq_a_share_topic_stock_extractions e
          ON e.group_id = t.group_id::text
         AND e.topic_id = t.topic_id::text
         AND e.stock_name ILIKE ?
        WHERE t.group_id::text = ?
          AND (
            e.stock_name IS NOT NULL
            OR t.title ILIKE ?
            OR tk.text ILIKE ?
            OR q.text ILIKE ?
            OR a.text ILIKE ?
          )
        ORDER BY t.create_time DESC
        LIMIT ?
    """


def _load_recommendation_counts(conn: Any, group_id: str, names: List[str]) -> Tuple[int, Dict[str, int]]:
    names = _ordered_unique([name for name in names if name], limit=10)
    if not names:
        return 0, {}

    conditions = " OR ".join("company ILIKE ?" for _ in names)
    params: List[Any] = [group_id]
    params.extend(f"%{name}%" for name in names)
    rows = conn.execute(
        f"""
        SELECT mention_date::text AS mention_date, SUM(mentions_count) AS count
        FROM zsxq_a_share_daily_mentions
        WHERE group_id = ?
          AND ({conditions})
        GROUP BY mention_date
        ORDER BY mention_date ASC
        """,
        params,
    ).fetchall()

    by_date = {str(row["mention_date"]): int(row["count"] or 0) for row in rows}
    return sum(by_date.values()), by_date


def _upsert_stock_topic_analysis(
    conn: Any,
    *,
    result: Dict[str, Any],
    status: str,
    error: str = "",
) -> None:
    topic_ids = [topic.get("topic_id") for topic in result.get("topics", [])]
    conn.execute(
        """
        INSERT INTO stock_topic_analyses (
            group_id, stock_name, stock_code, market, topic_ids_json,
            concepts_json, recommendation_count, summary_markdown, model,
            status, error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(group_id, stock_name) DO UPDATE SET
            stock_code = excluded.stock_code,
            market = excluded.market,
            topic_ids_json = excluded.topic_ids_json,
            concepts_json = excluded.concepts_json,
            recommendation_count = excluded.recommendation_count,
            summary_markdown = excluded.summary_markdown,
            model = excluded.model,
            status = excluded.status,
            error = excluded.error,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            result["group_id"],
            result["stock_name"],
            result.get("stock_code", ""),
            result.get("market", ""),
            _serialize_json_list(topic_ids),
            _serialize_json_list(result.get("concepts", [])),
            int(result.get("recommendation_count") or 0),
            result.get("summary_markdown", ""),
            result.get("model", ""),
            status,
            error,
        ),
    )
    conn.commit()


def get_latest_stock_topic_analysis(group_id: str, stock_name: str) -> Dict[str, Any] | None:
    query = _normalize_company_name(stock_name)
    if not query:
        raise ValueError("stock_name 不能为空")

    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT group_id, stock_name, stock_code, market, topic_ids_json,
                   concepts_json, recommendation_count, summary_markdown,
                   model, status, error, created_at, updated_at
            FROM stock_topic_analyses
            WHERE group_id = ?
              AND stock_name ILIKE ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_normalize_text(group_id), f"%{query}%"),
        ).fetchone()
        if not row:
            return None
        return {
            "group_id": row["group_id"],
            "stock_name": row["stock_name"],
            "stock_code": row["stock_code"] or "",
            "market": row["market"] or "",
            "topics": [],
            "concepts": _parse_json_list(row["concepts_json"]),
            "topic_count": len(_parse_json_list(row["topic_ids_json"])),
            "recommendation_count": int(row["recommendation_count"] or 0),
            "summary_markdown": row["summary_markdown"] or "",
            "model": row["model"] or "",
            "status": row["status"] or "",
            "error": row["error"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def search_stock_topics(group_id: str, stock_name: str, *, limit: int = MAX_MATCHED_TOPICS) -> Dict[str, Any]:
    query = _normalize_company_name(stock_name)
    if not query:
        raise ValueError("stock_name 不能为空")

    group_id_text = _normalize_text(group_id)
    like = f"%{query}%"
    conn = connect()
    try:
        rows = conn.execute(
            _build_topic_search_sql(),
            (like, group_id_text, like, like, like, like, max(1, min(int(limit), MAX_MATCHED_TOPICS))),
        ).fetchall()
        if not rows:
            return _empty_search_result(group_id_text, query)

        topics_by_id: Dict[str, Dict[str, Any]] = {}
        stock_names: List[str] = []
        stock_codes: List[str] = []
        markets: List[str] = []

        for row in rows:
            topic_id = str(row["topic_id"])
            topic = topics_by_id.setdefault(
                topic_id,
                {
                    "topic_id": topic_id,
                    "title": row["title"] or "",
                    "create_time": row["create_time"] or "",
                    "likes_count": int(row["likes_count"] or 0),
                    "comments_count": int(row["comments_count"] or 0),
                    "reading_count": int(row["reading_count"] or 0),
                    "content_preview": _clip(_topic_content(row), 260),
                    "concepts": [],
                    "reasons": [],
                    "confidence": 0.0,
                    "recommendation_count": 0,
                },
            )
            stock_names.append(row["stock_name"] or query)
            stock_codes.append(row["stock_code"] or "")
            markets.append(row["market"] or "")
            topic["concepts"] = _ordered_unique([*topic["concepts"], *_parse_json_list(row["concepts_json"])], limit=12)
            topic["reasons"] = _ordered_unique([*topic["reasons"], row["reason"]], limit=6)
            topic["confidence"] = max(_safe_float(topic["confidence"]), _safe_float(row["confidence"]))

        recommendation_count, recommendation_by_date = _load_recommendation_counts(
            conn,
            group_id_text,
            _ordered_unique([query, *stock_names], limit=10),
        )
        for topic in topics_by_id.values():
            topic_day = str(topic["create_time"] or "")[:10]
            topic["recommendation_count"] = recommendation_by_date.get(topic_day, 0)

        topics = sorted(topics_by_id.values(), key=lambda item: str(item["create_time"] or ""), reverse=True)
        concepts = _ordered_unique(
            concept
            for topic in topics
            for concept in topic.get("concepts", [])
        )
        stock_name_values = _ordered_unique(stock_names, limit=1)
        stock_code_values = _ordered_unique(stock_codes, limit=1)
        market_values = _ordered_unique(markets, limit=1)
        return {
            "group_id": group_id_text,
            "stock_name": stock_name_values[0] if stock_name_values else query,
            "stock_code": stock_code_values[0] if stock_code_values else "",
            "market": market_values[0] if market_values else "",
            "topics": topics,
            "concepts": concepts,
            "topic_count": len(topics),
            "recommendation_count": recommendation_count,
        }
    finally:
        conn.close()


def _build_analysis_topic_payload(search_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    topic_ids = [str(topic.get("topic_id") or "") for topic in search_result.get("topics", [])[:MAX_ANALYSIS_TOPICS]]
    if not topic_ids:
        return []

    conn = connect()
    try:
        placeholders = ",".join("?" for _ in topic_ids)
        rows = conn.execute(
            f"""
            SELECT
                t.topic_id,
                t.title,
                t.create_time,
                t.likes_count,
                t.comments_count,
                t.reading_count,
                tk.text AS talk_text,
                q.text AS question_text,
                a.text AS answer_text
            FROM topics t
            LEFT JOIN talks tk ON t.topic_id = tk.topic_id
            LEFT JOIN questions q ON t.topic_id = q.topic_id
            LEFT JOIN answers a ON t.topic_id = a.topic_id
            WHERE t.group_id::text = ?
              AND t.topic_id::text IN ({placeholders})
            ORDER BY t.create_time DESC
            """,
            [search_result["group_id"], *topic_ids],
        ).fetchall()
    finally:
        conn.close()

    concepts_by_topic = {
        str(topic.get("topic_id")): list(topic.get("concepts") or [])
        for topic in search_result.get("topics", [])
    }
    return [
        {
            "topic_id": str(row["topic_id"]),
            "title": row["title"] or "",
            "create_time": row["create_time"] or "",
            "metrics": {
                "likes_count": int(row["likes_count"] or 0),
                "comments_count": int(row["comments_count"] or 0),
                "reading_count": int(row["reading_count"] or 0),
            },
            "concepts": concepts_by_topic.get(str(row["topic_id"]), []),
            "content": _clip(_topic_content(row), MAX_TOPIC_TEXT_CHARS),
        }
        for row in rows
    ]


def _build_stock_analysis_prompt(search_result: Dict[str, Any], topics: List[Dict[str, Any]]) -> str:
    payload = {
        "group_id": search_result["group_id"],
        "stock_name": search_result["stock_name"],
        "stock_code": search_result.get("stock_code") or "",
        "market": search_result.get("market") or "",
        "recommendation_count": search_result.get("recommendation_count") or 0,
        "concepts": search_result.get("concepts") or [],
        "topic_count": len(topics),
        "topics": topics,
    }
    return _clip(json.dumps(payload, ensure_ascii=False, indent=2), MAX_ANALYSIS_PROMPT_CHARS)


def _call_stock_analysis_ai(prompt_payload: str) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    wire_api = _normalize_text(runtime_ai_config.get("wire_api")) or get_default_wire_api()
    reasoning_effort = get_summary_reasoning_effort()
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股社群话题分析助手。"
                "只基于用户提供的知识星球话题内容总结，不要补充外部行情或未出现的信息。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请基于输入话题，对这只股票生成中文 Markdown 分析。\n\n"
                "结构：\n"
                "## 一句话结论\n"
                "## 话题共识\n"
                "## 相关概念\n"
                "## 推荐热度\n"
                "## 主要风险或分歧\n"
                "## 来源话题索引\n\n"
                "要求：每条判断尽量引用 topic_id；如果证据不足，请直接说明。\n\n"
                f"输入数据：\n{prompt_payload}"
            ),
        },
    ]

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=180)
    if wire_api.strip().lower() == "responses":
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
        )
        return _extract_response_text(response).strip(), model

    response = client.chat.completions.create(model=model, messages=messages, stream=False)
    return _normalize_text(response.choices[0].message.content), model


def analyze_stock_topics(
    group_id: str,
    stock_name: str,
    *,
    limit: int = MAX_ANALYSIS_TOPICS,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    _log(log_callback, "📚 搜索股票相关话题...")
    search_result = search_stock_topics(group_id, stock_name, limit=limit)
    _log(log_callback, f"📊 命中话题: {search_result['topic_count']}，推荐次数: {search_result['recommendation_count']}")
    topics = _build_analysis_topic_payload(search_result)
    if not topics:
        result = {
            **search_result,
            "summary_markdown": "没有找到可分析的话题内容。",
            "model": "",
        }
        conn = connect()
        try:
            _upsert_stock_topic_analysis(conn, result=result, status="completed")
        finally:
            conn.close()
        return result

    _log(log_callback, f"🤖 调用 AI 分析前 {len(topics)} 条话题...")
    try:
        summary, model = _call_stock_analysis_ai(_build_stock_analysis_prompt(search_result, topics))
    except Exception as exc:
        failed_result = {
            **search_result,
            "topics": search_result["topics"][: len(topics)],
            "summary_markdown": "",
            "model": "",
        }
        conn = connect()
        try:
            _upsert_stock_topic_analysis(conn, result=failed_result, status="failed", error=str(exc))
        finally:
            conn.close()
        raise
    result = {
        **search_result,
        "topics": search_result["topics"][: len(topics)],
        "summary_markdown": summary or "AI 返回内容为空。",
        "model": model,
    }
    conn = connect()
    try:
        _upsert_stock_topic_analysis(conn, result=result, status="completed")
    finally:
        conn.close()
    _log(log_callback, "✅ 个股话题分析结果已保存")
    return result


__all__ = [
    "analyze_stock_topics",
    "get_latest_stock_topic_analysis",
    "search_stock_topics",
    "_normalize_company_name",
    "_parse_json_list",
]
