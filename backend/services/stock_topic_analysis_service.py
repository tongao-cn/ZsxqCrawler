"""Stock-scoped topic search and AI summary for a group."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Tuple

from openai import OpenAI

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.services.ai_json_utils import extract_json_object
from backend.services.stock_topic_analysis_ai_prompts import (
    build_image_stock_extraction_input,
    build_question_analysis_messages,
    build_question_keyword_messages,
    build_stock_analysis_messages,
)
from backend.services.stock_topic_analysis_payloads import (
    build_analysis_topic_payload,
    build_question_analysis_prompt,
    build_question_topic_payload,
    build_stock_analysis_prompt,
    require_topic_excerpt,
)
from backend.services.stock_topic_analysis_queries import (
    build_question_topic_search_sql,
    build_topic_search_sql,
)
from backend.services.daily_topic_analysis_service import _clip, _extract_response_text
from backend.storage.db_compat import connect


MAX_SEARCH_CANDIDATE_TOPICS = 500
MAX_ANALYSIS_TOPICS = 30
MAX_ANALYSIS_TOPICS_PER_CALL = 10
MAX_TRACKED_TOPIC_IDS = 5000
MAX_TOPIC_TEXT_CHARS = 1800
MAX_ANALYSIS_PROMPT_CHARS = 50000
MAX_BATCH_STOCKS = 50
MAX_BATCH_STOCK_ANALYSIS_WORKERS = 10
MAX_QUESTION_KEYWORDS = 8
MAX_QUESTION_TOPICS = 60
MAX_EXTRACT_IMAGE_BYTES = 4 * 1024 * 1024
STOCK_TOPIC_ANALYSIS_TABLE = "stock_topic_analyses"
PROCESSED_TOPIC_STATUSES = {"analyzed", "skipped"}
SUPPORTED_EXTRACT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


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


def parse_stock_names(values: Any, *, limit: int = MAX_BATCH_STOCKS) -> List[str]:
    if isinstance(values, str):
        raw_values = re.split(r"[\s,，、;；]+", values)
    elif isinstance(values, Iterable):
        raw_values = []
        for value in values:
            raw_values.extend(re.split(r"[\s,，、;；]+", _normalize_text(value)))
    else:
        raw_values = []
    return _ordered_unique((_normalize_company_name(value) for value in raw_values), limit=max(1, min(limit, MAX_BATCH_STOCKS)))


def _normalize_question_keywords(values: Any, *, limit: int = MAX_QUESTION_KEYWORDS) -> List[str]:
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, Iterable):
        raw_values = list(values)
    else:
        raw_values = []
    return _ordered_unique(
        (_normalize_text(value) for value in raw_values),
        limit=max(1, min(limit, MAX_QUESTION_KEYWORDS)),
    )


def _parse_image_data_url(image_data_url: str) -> Tuple[str, str, bytes]:
    value = _normalize_text(image_data_url)
    match = re.fullmatch(r"data:([^;,]+);base64,(.+)", value, flags=re.DOTALL)
    if not match:
        raise ValueError("图片数据格式不正确")

    mime_type = match.group(1).strip().lower()
    if mime_type not in SUPPORTED_EXTRACT_IMAGE_TYPES:
        raise ValueError("仅支持 JPG、PNG 或 WebP 图片")

    import base64
    import binascii

    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise ValueError("图片 base64 数据不正确") from exc
    if not image_bytes:
        raise ValueError("图片内容为空")
    if len(image_bytes) > MAX_EXTRACT_IMAGE_BYTES:
        raise ValueError("图片不能超过 4MB")
    return mime_type, value, image_bytes


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
        "processed_topic_ids": [],
        "analyzed_topic_ids": [],
        "skipped_topic_ids": [],
    }


def _empty_latest_result(group_id: str, stock_name: str) -> Dict[str, Any]:
    return {
        **_empty_search_result(group_id, stock_name),
        "summary_markdown": "",
        "model": "",
        "status": "missing",
        "error": "",
        "created_at": None,
        "updated_at": None,
    }


def _serialize_json_list(values: Iterable[Any]) -> str:
    return json.dumps(_ordered_unique(values, limit=MAX_TRACKED_TOPIC_IDS), ensure_ascii=False)


def _topic_ids_from_result(result: Dict[str, Any]) -> List[str]:
    return _ordered_unique((topic.get("topic_id") for topic in result.get("topics", [])), limit=MAX_TRACKED_TOPIC_IDS)


def _merge_topic_ids(*groups: Iterable[Any]) -> List[str]:
    merged: List[Any] = []
    for group in groups:
        merged.extend(list(group or []))
    return _ordered_unique(merged, limit=MAX_TRACKED_TOPIC_IDS)


def _exclude_topic_ids(values: Iterable[Any], excluded: Iterable[Any]) -> List[str]:
    excluded_set = _topic_id_set(excluded)
    return _ordered_unique((value for value in values if str(value) not in excluded_set), limit=MAX_TRACKED_TOPIC_IDS)


def _topic_id_set(values: Iterable[Any]) -> set[str]:
    return {str(value) for value in _ordered_unique(values, limit=MAX_TRACKED_TOPIC_IDS)}


def _chunks(values: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _recent_topic_cutoff_text() -> str:
    return (date.today() - timedelta(days=365)).isoformat()


def _build_stock_alias_terms(stock_name: Any, stock_code: Any = "", market: Any = "") -> List[str]:
    name = _normalize_text(stock_name)
    normalized_name = _normalize_company_name(name)
    code = _normalize_text(stock_code)
    market_text = _normalize_text(market)
    terms = [name, normalized_name, code]
    if market_text and code:
        terms.extend([f"{market_text}.{code}", f"{market_text}{code}"])
    return _ordered_unique((term for term in terms if term), limit=10)


def _require_topic_excerpt(value: Any, *, topic_id: Any, stock_name: Any) -> str:
    return require_topic_excerpt(value, topic_id=topic_id, stock_name=stock_name)


def _score_relevant_topic(extracted_content: str, mode: str, matched_terms: Iterable[str], topic_row: Dict[str, Any]) -> int:
    if not extracted_content:
        return 0
    score = 100 if mode in {"full", "title_full"} else 70
    score += min(len(_ordered_unique(matched_terms, limit=10)) * 5, 15)
    confidence = _safe_float(topic_row.get("confidence"))
    if confidence > 0:
        score += min(int(confidence * 10), 10)
    return score


def _empty_topic_summary(topic_id: Any) -> Dict[str, Any]:
    return {
        "topic_id": _normalize_text(topic_id),
        "title": "",
        "create_time": "",
        "likes_count": 0,
        "comments_count": 0,
        "reading_count": 0,
        "content_preview": "",
        "concepts": [],
        "reasons": [],
        "excerpt": "",
        "confidence": 0.0,
        "recommendation_count": 0,
    }


def _load_topic_summaries(conn: Any, group_id: str, topic_ids: List[str], stock_name: str = "") -> List[Dict[str, Any]]:
    if not topic_ids:
        return []
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
            a.text AS answer_text,
            e.excerpt
        FROM topics t
        LEFT JOIN talks tk ON t.topic_id = tk.topic_id
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        LEFT JOIN zsxq_a_share_topic_stock_extractions e
          ON e.group_id = t.group_id::text
         AND e.topic_id = t.topic_id::text
         AND e.stock_name ILIKE ?
        WHERE t.group_id::text = ?
          AND t.topic_id::text IN ({placeholders})
        ORDER BY t.create_time DESC
        """,
        [f"%{_normalize_company_name(stock_name)}%", group_id, *topic_ids],
    ).fetchall()
    summaries: List[Dict[str, Any]] = []
    for row in rows:
        excerpt = _require_topic_excerpt(row["excerpt"], topic_id=row["topic_id"], stock_name=stock_name)
        summaries.append(
            {
                "topic_id": str(row["topic_id"]),
                "title": row["title"] or "",
                "create_time": row["create_time"] or "",
                "likes_count": int(row["likes_count"] or 0),
                "comments_count": int(row["comments_count"] or 0),
                "reading_count": int(row["reading_count"] or 0),
                "excerpt": excerpt,
                "content_preview": _clip(excerpt, 260),
                "concepts": [],
                "reasons": [],
                "confidence": 0.0,
                "recommendation_count": 0,
            }
        )
    found = {topic["topic_id"] for topic in summaries}
    summaries.extend(_empty_topic_summary(topic_id) for topic_id in topic_ids if str(topic_id) not in found)
    return summaries


def _load_latest_processed_topic_ids(conn: Any, group_id: str, stock_name: str) -> List[str]:
    query = _normalize_company_name(stock_name)
    if not query:
        return []
    state_ids = _load_stock_topic_processed_state_ids(conn, group_id, query)
    if state_ids:
        return state_ids
    try:
        row = conn.execute(
            """
            SELECT topic_ids_json
            FROM stock_topic_analyses
            WHERE group_id = ?
              AND stock_name ILIKE ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_normalize_text(group_id), f"%{query}%"),
        ).fetchone()
    except Exception:
        conn.rollback()
        return []
    if not row:
        return []
    try:
        return _parse_json_list(row["topic_ids_json"])
    except Exception:
        conn.rollback()
        return []


def _load_stock_topic_processed_state_ids(conn: Any, group_id: str, stock_name: str) -> List[str]:
    placeholders = ",".join("?" for _ in PROCESSED_TOPIC_STATUSES)
    try:
        rows = conn.execute(
            f"""
            SELECT topic_id
            FROM stock_topic_processed_states
            WHERE group_id = ?
              AND stock_name ILIKE ?
              AND status IN ({placeholders})
            ORDER BY updated_at ASC
            """,
            [_normalize_text(group_id), f"%{_normalize_company_name(stock_name)}%", *sorted(PROCESSED_TOPIC_STATUSES)],
        ).fetchall()
    except Exception:
        conn.rollback()
        return []
    return _ordered_unique((row["topic_id"] for row in rows), limit=MAX_TRACKED_TOPIC_IDS)


def _upsert_stock_topic_processed_states(
    conn: Any,
    *,
    group_id: str,
    stock_name: str,
    topic_ids: Iterable[Any],
    status: str,
    extract_mode: str = "",
    model: str = "",
    error: str = "",
) -> None:
    normalized_topic_ids = _ordered_unique(topic_ids, limit=MAX_TRACKED_TOPIC_IDS)
    if not normalized_topic_ids:
        return
    params = [
        (
            _normalize_text(group_id),
            _normalize_company_name(stock_name),
            topic_id,
            status,
            extract_mode,
            model,
            error,
        )
        for topic_id in normalized_topic_ids
    ]
    for row in params:
        conn.execute(
            """
            INSERT INTO stock_topic_processed_states (
                group_id, stock_name, topic_id, status, extract_mode, model,
                error, processed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(group_id, stock_name, topic_id) DO UPDATE SET
                status = excluded.status,
                extract_mode = excluded.extract_mode,
                model = excluded.model,
                error = excluded.error,
                processed_at = excluded.processed_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            row,
        )


def _build_topic_search_sql(*, recent_cutoff: str | None = None) -> str:
    return build_topic_search_sql(recent_cutoff=recent_cutoff)


def _build_question_topic_search_sql(keyword_count: int, *, recent_cutoff: str | None = None) -> str:
    return build_question_topic_search_sql(keyword_count, recent_cutoff=recent_cutoff)


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
    analyzed_topic_ids: Iterable[Any] | None = None,
    processed_state_topic_ids: Iterable[Any] | None = None,
    processed_topic_status: str = "analyzed",
    extract_mode: str = "",
    write_processed_state: bool = True,
    commit: bool = True,
) -> None:
    topic_ids = list(analyzed_topic_ids) if analyzed_topic_ids is not None else _topic_ids_from_result(result)
    if write_processed_state:
        state_topic_ids = list(processed_state_topic_ids) if processed_state_topic_ids is not None else topic_ids
        _upsert_stock_topic_processed_states(
            conn,
            group_id=result["group_id"],
            stock_name=result["stock_name"],
            topic_ids=state_topic_ids,
            status=processed_topic_status,
            extract_mode=extract_mode,
            model=result.get("model", ""),
            error=error,
        )
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
    if commit:
        conn.commit()


def _insert_stock_topic_analysis_version(
    conn: Any,
    *,
    result: Dict[str, Any],
    status: str,
    error: str = "",
    analyzed_topic_ids: Iterable[Any] | None = None,
) -> None:
    topic_ids = list(analyzed_topic_ids) if analyzed_topic_ids is not None else _topic_ids_from_result(result)
    conn.execute(
        """
        INSERT INTO stock_topic_analysis_versions (
            group_id, stock_name, stock_code, market, topic_ids_json,
            concepts_json, recommendation_count, summary_markdown, model,
            status, error, analysis_mode, new_topic_count, analysis_date,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
            result.get("analysis_mode", ""),
            int(result.get("new_topic_count") or 0),
            date.today().isoformat(),
        ),
    )


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
        topic_ids = _parse_json_list(row["topic_ids_json"])
        topics = _load_topic_summaries(conn, _normalize_text(row["group_id"]), topic_ids, row["stock_name"])
        return {
            "group_id": row["group_id"],
            "stock_name": row["stock_name"],
            "stock_code": row["stock_code"] or "",
            "market": row["market"] or "",
            "topics": topics,
            "concepts": _parse_json_list(row["concepts_json"]),
            "topic_count": len(topic_ids),
            "recommendation_count": int(row["recommendation_count"] or 0),
            "summary_markdown": row["summary_markdown"] or "",
            "model": row["model"] or "",
            "status": row["status"] or "",
            "error": row["error"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "processed_topic_ids": topic_ids,
            "analyzed_topic_ids": topic_ids,
            "new_topic_count": 0,
            "analysis_mode": "saved",
        }
    finally:
        conn.close()


def get_latest_stock_topic_analyses(group_id: str, stock_names: Any) -> Dict[str, Any]:
    names = parse_stock_names(stock_names)
    if not names:
        raise ValueError("stock_names 不能为空")

    group_id_text = _normalize_text(group_id)
    return {
        "group_id": group_id_text,
        "stocks": [
            get_latest_stock_topic_analysis(group_id_text, stock_name) or _empty_latest_result(group_id_text, stock_name)
            for stock_name in names
        ],
    }


def search_stock_topics(group_id: str, stock_name: str, *, limit: int | None = None) -> Dict[str, Any]:
    query = _normalize_company_name(stock_name)
    if not query:
        raise ValueError("stock_name 不能为空")

    group_id_text = _normalize_text(group_id)
    alias_terms = _build_stock_alias_terms(stock_name)
    search_term = alias_terms[0] if alias_terms else query
    like = f"%{search_term}%"
    recent_cutoff = _recent_topic_cutoff_text()
    conn = connect()
    try:
        processed_topic_ids = _load_latest_processed_topic_ids(conn, group_id_text, query)
        processed_topic_id_set = set(processed_topic_ids)
        rows = conn.execute(
            _build_topic_search_sql(recent_cutoff=recent_cutoff),
            (like, group_id_text, recent_cutoff, MAX_SEARCH_CANDIDATE_TOPICS),
        ).fetchall()
        if not rows:
            empty_result = _empty_search_result(group_id_text, query)
            empty_result["processed_topic_ids"] = processed_topic_ids
            empty_result["analyzed_topic_ids"] = processed_topic_ids
            return empty_result

        topics_by_id: Dict[str, Dict[str, Any]] = {}
        stock_names: List[str] = []
        stock_codes: List[str] = []
        markets: List[str] = []

        for row in rows:
            topic_id = str(row["topic_id"])
            if topic_id in processed_topic_id_set:
                continue
            stored_excerpt = _require_topic_excerpt(row["excerpt"], topic_id=topic_id, stock_name=query)
            extracted_content = stored_excerpt
            mode = "stored_excerpt"
            matched_terms = _ordered_unique([_normalize_text(row["stock_name"]), *alias_terms], limit=10)
            topic = topics_by_id.setdefault(
                topic_id,
                {
                    "topic_id": topic_id,
                    "title": row["title"] or "",
                    "create_time": row["create_time"] or "",
                    "likes_count": int(row["likes_count"] or 0),
                    "comments_count": int(row["comments_count"] or 0),
                    "reading_count": int(row["reading_count"] or 0),
                    "content_preview": _clip(extracted_content, 260),
                    "concepts": [],
                    "reasons": [],
                    "excerpt": stored_excerpt,
                    "confidence": 0.0,
                    "recommendation_count": 0,
                    "extract_mode": mode,
                    "relevance_score": 0,
                    "analysis_content": extracted_content,
                },
            )
            stock_names.append(row["stock_name"] or query)
            stock_codes.append(row["stock_code"] or "")
            markets.append(row["market"] or "")
            topic["concepts"] = _ordered_unique([*topic["concepts"], *_parse_json_list(row["concepts_json"])], limit=12)
            topic["reasons"] = _ordered_unique([*topic["reasons"], row["reason"]], limit=6)
            topic["confidence"] = max(_safe_float(topic["confidence"]), _safe_float(row["confidence"]))
            topic["relevance_score"] = max(
                int(topic["relevance_score"]),
                _score_relevant_topic(extracted_content, mode, matched_terms, topic),
            )
            topic["extract_mode"] = mode if topic.get("extract_mode") != "full" else topic["extract_mode"]
            if len(extracted_content) > len(str(topic.get("analysis_content") or "")):
                topic["analysis_content"] = extracted_content

        recommendation_count, recommendation_by_date = _load_recommendation_counts(
            conn,
            group_id_text,
            _ordered_unique([query, *stock_names], limit=10),
        )
        for topic in topics_by_id.values():
            topic_day = str(topic["create_time"] or "")[:10]
            topic["recommendation_count"] = recommendation_by_date.get(topic_day, 0)

        topics = sorted(
            topics_by_id.values(),
            key=lambda item: (
                int(item.get("relevance_score") or 0),
                str(item["create_time"] or ""),
            ),
            reverse=True,
        )
        if limit is not None:
            topics = topics[: max(1, int(limit))]
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
            "processed_topic_ids": _ordered_unique(processed_topic_ids, limit=MAX_TRACKED_TOPIC_IDS),
            "analyzed_topic_ids": _ordered_unique(processed_topic_ids, limit=MAX_TRACKED_TOPIC_IDS),
            "skipped_topic_ids": [],
        }
    finally:
        conn.close()


def search_stock_question_topics(group_id: str, question: str, *, limit: int = MAX_QUESTION_TOPICS) -> Dict[str, Any]:
    question_text = _normalize_text(question)
    if not question_text:
        raise ValueError("question 不能为空")
    keywords, keyword_model = _call_question_keyword_ai(question_text)
    if not keywords:
        raise ValueError("无法从问题中提取关键词")

    group_id_text = _normalize_text(group_id)
    params: List[Any] = [group_id_text]
    for keyword in keywords:
        like = f"%{keyword}%"
        params.extend([like, like, like, like])
    recent_cutoff = _recent_topic_cutoff_text()
    params.append(recent_cutoff)
    params.append(max(1, min(int(limit), MAX_QUESTION_TOPICS)))

    conn = connect()
    try:
        rows = conn.execute(
            _build_question_topic_search_sql(len(keywords), recent_cutoff=recent_cutoff),
            params,
        ).fetchall()
    finally:
        conn.close()

    topics_by_id: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        topic_id = str(row["topic_id"])
        content = _topic_content(row)
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in content.lower()]
        topics_by_id[topic_id] = {
            "topic_id": topic_id,
            "title": row["title"] or "",
            "create_time": row["create_time"] or "",
            "likes_count": int(row["likes_count"] or 0),
            "comments_count": int(row["comments_count"] or 0),
            "reading_count": int(row["reading_count"] or 0),
            "content_preview": _clip(content, 300),
            "matched_keywords": matched_keywords,
        }

    topics = sorted(topics_by_id.values(), key=lambda item: str(item["create_time"] or ""), reverse=True)
    return {
        "group_id": group_id_text,
        "question": question_text,
        "keywords": keywords,
        "keyword_model": keyword_model,
        "topics": topics,
        "topic_count": len(topics),
    }


def _build_analysis_topic_payload(search_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return build_analysis_topic_payload(search_result)


def _build_question_topic_payload(search_result: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    return build_question_topic_payload(
        rows,
        keywords=list(search_result.get("keywords") or []),
        max_topic_text_chars=MAX_TOPIC_TEXT_CHARS,
    )


def _build_stock_analysis_prompt(
    search_result: Dict[str, Any],
    topics: List[Dict[str, Any]],
    *,
    existing_summary: str = "",
) -> str:
    return build_stock_analysis_prompt(
        search_result,
        topics,
        existing_summary=existing_summary,
        max_analysis_prompt_chars=MAX_ANALYSIS_PROMPT_CHARS,
    )


def _build_question_analysis_prompt(search_result: Dict[str, Any], topics: List[Dict[str, Any]]) -> str:
    return build_question_analysis_prompt(
        search_result,
        topics,
        max_analysis_prompt_chars=MAX_ANALYSIS_PROMPT_CHARS,
    )


def _call_stock_analysis_ai(prompt_payload: str, *, incremental: bool = False) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    reasoning_effort = get_summary_reasoning_effort()
    messages = build_stock_analysis_messages(prompt_payload)

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=180)
    response = client.responses.create(
        model=model,
        input=messages,
        reasoning={"effort": reasoning_effort},
    )
    return _extract_response_text(response).strip(), model


def _extract_json_object(text: str) -> Dict[str, Any]:
    return extract_json_object(text)


def _call_question_keyword_ai(question: str) -> Tuple[List[str], str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    reasoning_effort = get_summary_reasoning_effort()
    messages = build_question_keyword_messages(question)

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=120)
    response = client.responses.create(
        model=model,
        input=messages,
        reasoning={"effort": reasoning_effort},
    )
    text = _extract_response_text(response)

    parsed = _extract_json_object(text)
    keywords = _normalize_question_keywords(parsed.get("keywords") or parsed.get("keyword") or [])
    if not keywords:
        raise ValueError("AI 未能从问题中提取检索关键词")
    return keywords, model


def _call_question_analysis_ai(question: str, prompt_payload: str) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    reasoning_effort = get_summary_reasoning_effort()
    messages = build_question_analysis_messages(question, prompt_payload)

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=180)
    response = client.responses.create(
        model=model,
        input=messages,
        reasoning={"effort": reasoning_effort},
    )
    return _extract_response_text(response).strip(), model


def extract_stock_names_from_image(image_data_url: str) -> Dict[str, Any]:
    mime_type, normalized_data_url, image_bytes = _parse_image_data_url(image_data_url)
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    reasoning_effort = get_summary_reasoning_effort()
    prompt = (
        "请从这张图片中提取出现的 A 股股票名称。"
        "只输出 JSON，不要 Markdown，不要解释。"
        "如果识别到股票，JSON 结构为 {\"stockNames\": [\"股票名1\", \"股票名2\"]}。"
        "如果图片中没有明确股票名称，JSON 结构为 {\"error\": \"NO_STOCKS\"}。"
        "要求：保留图片里的股票中文简称，去重，最多 50 个。"
    )

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=120)
    response = client.responses.create(
        model=model,
        input=build_image_stock_extraction_input(prompt, normalized_data_url),
        reasoning={"effort": reasoning_effort},
    )
    text = _extract_response_text(response)

    parsed = _extract_json_object(text)
    if parsed:
        stock_names = parse_stock_names(parsed.get("stockNames") or parsed.get("stock_names") or [])
    else:
        stock_names = parse_stock_names(text)
    if not stock_names:
        raise ValueError("图片里没有识别到明确股票名称")
    return {
        "stockNames": stock_names,
        "model": model,
        "mime_type": mime_type,
        "image_bytes": len(image_bytes),
    }


def analyze_stock_topics(
    group_id: str,
    stock_name: str,
    *,
    limit: int | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    _log(log_callback, "📚 搜索股票相关话题...")
    search_result = search_stock_topics(group_id, stock_name, limit=limit)
    _log(log_callback, f"📊 命中话题: {search_result['topic_count']}，推荐次数: {search_result['recommendation_count']}")
    latest = get_latest_stock_topic_analysis(group_id, stock_name)
    saved_topic_ids = list((latest or {}).get("processed_topic_ids") or (latest or {}).get("analyzed_topic_ids") or [])
    current_topic_ids = _topic_ids_from_result(search_result)
    new_topic_ids = [topic_id for topic_id in current_topic_ids if topic_id not in _topic_id_set(saved_topic_ids)]
    new_skipped_topic_ids = _exclude_topic_ids(search_result.get("skipped_topic_ids") or [], saved_topic_ids)
    processed_topic_ids = _merge_topic_ids(saved_topic_ids, search_result.get("processed_topic_ids") or [], new_skipped_topic_ids)
    has_new_processed_topic_ids = len(_topic_id_set(processed_topic_ids)) > len(_topic_id_set(saved_topic_ids))
    has_existing_summary = bool((latest or {}).get("summary_markdown"))

    if has_existing_summary and not new_topic_ids:
        result = {
            **search_result,
            "summary_markdown": latest.get("summary_markdown", ""),
            "model": latest.get("model", ""),
            "status": latest.get("status", "completed"),
            "error": latest.get("error", ""),
            "created_at": latest.get("created_at"),
            "updated_at": latest.get("updated_at"),
            "processed_topic_ids": processed_topic_ids,
            "analyzed_topic_ids": saved_topic_ids,
            "new_topic_count": 0,
            "analysis_mode": "up_to_date",
        }
        if has_new_processed_topic_ids:
            conn = connect()
            try:
                _upsert_stock_topic_analysis(
                    conn,
                    result=result,
                    status="completed",
                    analyzed_topic_ids=processed_topic_ids,
                    processed_state_topic_ids=new_skipped_topic_ids,
                    processed_topic_status="skipped",
                )
            finally:
                conn.close()
        _log(log_callback, "✅ 没有新话题，沿用已保存的个股分析结果")
        return result

    topics = _build_analysis_topic_payload(search_result)
    if new_topic_ids:
        new_topic_id_set = set(new_topic_ids)
        topics = [topic for topic in topics if topic.get("topic_id") in new_topic_id_set]

    if not topics:
        processed_topic_ids = _merge_topic_ids(processed_topic_ids, current_topic_ids)
        result = {
            **search_result,
            "summary_markdown": (latest or {}).get("summary_markdown") or "没有找到可分析的话题内容。",
            "model": (latest or {}).get("model", ""),
            "status": "completed",
            "processed_topic_ids": processed_topic_ids,
            "analyzed_topic_ids": saved_topic_ids,
            "new_topic_count": 0,
            "analysis_mode": "up_to_date" if has_existing_summary else "initialize",
        }
        conn = connect()
        try:
            _upsert_stock_topic_analysis(
                conn,
                result=result,
                status="completed",
                analyzed_topic_ids=processed_topic_ids,
                processed_state_topic_ids=new_skipped_topic_ids,
                processed_topic_status="skipped",
            )
        finally:
            conn.close()
        return result

    analysis_mode = "incremental" if has_existing_summary else "initialize"
    topic_batches = _chunks(topics, MAX_ANALYSIS_TOPICS_PER_CALL)
    _log(
        log_callback,
        f"🤖 调用 AI {'增量更新' if analysis_mode == 'incremental' else '初始化分析'} {len(topics)} 条话题，分 {len(topic_batches)} 批...",
    )
    try:
        summary = (latest or {}).get("summary_markdown") or ""
        model = (latest or {}).get("model") or ""
        processed_topic_ids = list(processed_topic_ids)
        current_batch_topic_ids: List[str] = []
        for batch_index, topic_batch in enumerate(topic_batches, start=1):
            _log(log_callback, f"🤖 AI 分析批次 {batch_index}/{len(topic_batches)}，话题 {len(topic_batch)} 条")
            current_batch_topic_ids = [str(topic.get("topic_id") or "") for topic in topic_batch]
            summary, model = _call_stock_analysis_ai(
                _build_stock_analysis_prompt(
                    search_result,
                    topic_batch,
                    existing_summary=summary,
                ),
                incremental=bool(summary),
            )
            processed_topic_ids = _merge_topic_ids(processed_topic_ids, current_batch_topic_ids)
            checkpoint_result = {
                **search_result,
                "summary_markdown": summary or "",
                "model": model,
                "status": "running" if batch_index < len(topic_batches) else "completed",
                "processed_topic_ids": processed_topic_ids,
                "analyzed_topic_ids": processed_topic_ids,
                "new_topic_count": len(topics),
                "analysis_mode": analysis_mode,
            }
            conn = connect()
            try:
                _upsert_stock_topic_analysis(
                    conn,
                    result=checkpoint_result,
                    status=checkpoint_result["status"],
                    analyzed_topic_ids=processed_topic_ids,
                    processed_state_topic_ids=current_batch_topic_ids,
                    processed_topic_status="analyzed",
                )
            finally:
                conn.close()
    except Exception as exc:
        failed_topic_ids = current_batch_topic_ids or new_topic_ids
        failed_result = {
            **search_result,
            "topics": search_result["topics"][: len(topics)],
            "summary_markdown": (latest or {}).get("summary_markdown") or "",
            "model": (latest or {}).get("model", ""),
            "processed_topic_ids": processed_topic_ids,
            "analyzed_topic_ids": processed_topic_ids,
            "new_topic_count": len(topics),
            "analysis_mode": analysis_mode,
        }
        conn = connect()
        try:
            _upsert_stock_topic_analysis(
                conn,
                result=failed_result,
                status="failed",
                error=str(exc),
                analyzed_topic_ids=processed_topic_ids,
                processed_state_topic_ids=failed_topic_ids,
                processed_topic_status="failed",
            )
        finally:
            conn.close()
        raise
    processed_topic_ids = _merge_topic_ids(processed_topic_ids, (topic.get("topic_id") for topic in topics))
    result = {
        **search_result,
        "topics": search_result["topics"],
        "summary_markdown": summary or "AI 返回内容为空。",
        "model": model,
        "status": "completed",
        "processed_topic_ids": processed_topic_ids,
        "analyzed_topic_ids": processed_topic_ids,
        "new_topic_count": len(topics),
        "analysis_mode": analysis_mode,
    }
    conn = connect()
    try:
        _upsert_stock_topic_analysis(
            conn,
            result=result,
            status="completed",
            analyzed_topic_ids=processed_topic_ids,
            write_processed_state=False,
            commit=False,
        )
        _insert_stock_topic_analysis_version(
            conn,
            result=result,
            status="completed",
            analyzed_topic_ids=processed_topic_ids,
        )
        conn.commit()
    finally:
        conn.close()
    _log(log_callback, "✅ 个股分析结果已保存")
    return result


def analyze_stock_topics_batch(
    group_id: str,
    stock_names: Any,
    *,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    names = parse_stock_names(stock_names)
    if not names:
        raise ValueError("stock_names 不能为空")

    group_id_text = _normalize_text(group_id)
    total = len(names)
    results: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    no_topic_count = 0
    max_workers = min(MAX_BATCH_STOCK_ANALYSIS_WORKERS, total)
    _log(log_callback, f"开始批量分析，共 {total} 只股票，并发 {max_workers}")

    def analyze_one(index: int, stock_name: str) -> Tuple[int, Dict[str, Any], str]:
        try:
            preview = search_stock_topics(group_id_text, stock_name)
            if preview["topic_count"] <= 0:
                _log(log_callback, f"{index}/{total} {stock_name}: 未命中话题，保存空结果")
            else:
                _log(log_callback, f"{index}/{total} {stock_name}: 命中 {preview['topic_count']} 个话题，开始 AI 分析")

            result = analyze_stock_topics(
                group_id_text,
                stock_name,
                log_callback=log_callback,
            )
            _log(log_callback, f"{index}/{total} {result.get('stock_name') or stock_name}: 完成并保存")
            status = "no_topics" if result.get("topic_count", 0) <= 0 else "success"
            return index, result, status
        except Exception as exc:
            latest = get_latest_stock_topic_analysis(group_id_text, stock_name) or _empty_latest_result(group_id_text, stock_name)
            failed_result = {
                **latest,
                "status": "failed",
                "error": str(exc),
            }
            _log(log_callback, f"{index}/{total} {stock_name}: 失败 - {str(exc)}")
            return index, failed_result, "failed"

    ordered_results: List[Dict[str, Any] | None] = [None] * total
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(analyze_one, index, stock_name)
            for index, stock_name in enumerate(names, start=1)
        ]
        for future in as_completed(futures):
            index, result, status = future.result()
            ordered_results[index - 1] = result
            if status == "no_topics":
                no_topic_count += 1
            elif status == "failed":
                failed_count += 1
            else:
                success_count += 1

    results = [result for result in ordered_results if result is not None]
    _log(log_callback, f"批量分析完成：成功 {success_count}，失败 {failed_count}，无话题 {no_topic_count}")
    return {
        "group_id": group_id_text,
        "stocks": results,
        "summary": {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "no_topics": no_topic_count,
        },
    }


def answer_stock_question(
    group_id: str,
    question: str,
    *,
    log_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    _log(log_callback, "🔎 根据问题关键词搜索话题...")
    search_result = search_stock_question_topics(group_id, question)
    _log(
        log_callback,
        f"📚 关键词: {'、'.join(search_result['keywords'])}；命中话题: {search_result['topic_count']}",
    )
    topics = _build_question_topic_payload(search_result)
    if not topics:
        return {
            **search_result,
            "summary_markdown": "没有找到可回答该问题的话题内容。",
            "model": "",
            "status": "completed",
        }

    _log(log_callback, f"🤖 调用 AI 总结前 {len(topics)} 条话题...")
    summary, model = _call_question_analysis_ai(
        search_result["question"],
        _build_question_analysis_prompt(search_result, topics),
    )
    _log(log_callback, "✅ A股问答总结完成")
    return {
        **search_result,
        "topics": search_result["topics"][: len(topics)],
        "summary_markdown": summary or "AI 返回内容为空。",
        "model": model,
        "status": "completed",
    }


__all__ = [
    "answer_stock_question",
    "analyze_stock_topics",
    "analyze_stock_topics_batch",
    "extract_stock_names_from_image",
    "get_latest_stock_topic_analysis",
    "get_latest_stock_topic_analyses",
    "parse_stock_names",
    "search_stock_question_topics",
    "search_stock_topics",
    "_call_question_keyword_ai",
    "_parse_image_data_url",
    "_normalize_company_name",
    "_normalize_question_keywords",
    "_parse_json_list",
]
