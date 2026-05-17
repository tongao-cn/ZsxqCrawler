"""Stock-scoped topic search and AI summary for a group."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
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


MAX_SEARCH_CANDIDATE_TOPICS = 500
MAX_ANALYSIS_TOPICS = 30
MAX_ANALYSIS_TOPICS_PER_CALL = 10
MAX_TRACKED_TOPIC_IDS = 5000
MAX_TOPIC_TEXT_CHARS = 1800
MAX_ANALYSIS_PROMPT_CHARS = 50000
MAX_BATCH_STOCKS = 20
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


def _split_topic_text_segments(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    segments = [segment.strip() for segment in re.findall(r"[^。！？!?；;\n\r]+[。！？!?；;\n\r]*", normalized) if segment.strip()]
    return segments or [normalized]


def _count_term_hits(text: str, terms: Iterable[str]) -> int:
    normalized = _normalize_text(text)
    if not normalized:
        return 0
    return sum(1 for term in _ordered_unique(terms, limit=10) if term and term in normalized)


def _extract_relevant_topic_content(title: Any, body: Any, terms: Iterable[str]) -> tuple[str, str, List[str]]:
    title_text = _normalize_text(title)
    body_text = _normalize_text(body)
    full_text = "\n".join(part for part in (title_text, body_text) if part)
    if not full_text:
        return "", "empty", []

    alias_terms = _ordered_unique(terms, limit=10)
    matched_terms = [term for term in alias_terms if term in full_text]
    if not matched_terms:
        if title_text and any(term in title_text for term in alias_terms):
            return full_text, "title_full", alias_terms
        return "", "irrelevant", []

    if not body_text:
        return full_text, "title_full", matched_terms

    segments = _split_topic_text_segments(body_text)
    if len(body_text) <= 600 or len(segments) <= 2:
        return full_text, "full", matched_terms

    matched_indices = [
        index
        for index, segment in enumerate(segments)
        if any(term in segment for term in matched_terms)
    ]
    if not matched_indices:
        return full_text, "full", matched_terms

    if len(matched_indices) / max(1, len(segments)) >= 0.5:
        return full_text, "full", matched_terms

    chosen_indices: List[int] = []
    for index in matched_indices:
        for neighbor in range(max(0, index - 1), min(len(segments), index + 2)):
            if neighbor not in chosen_indices:
                chosen_indices.append(neighbor)
    chosen_indices.sort()
    excerpt = "".join(segments[index] for index in chosen_indices)
    if title_text:
        excerpt = f"{title_text}\n{excerpt}"
    return excerpt, "snippet", matched_terms


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
        "confidence": 0.0,
        "recommendation_count": 0,
    }


def _load_topic_summaries(conn: Any, group_id: str, topic_ids: List[str]) -> List[Dict[str, Any]]:
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
            a.text AS answer_text
        FROM topics t
        LEFT JOIN talks tk ON t.topic_id = tk.topic_id
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        WHERE t.group_id::text = ?
          AND t.topic_id::text IN ({placeholders})
        ORDER BY t.create_time DESC
        """,
        [group_id, *topic_ids],
    ).fetchall()
    summaries = [
        {
            "topic_id": str(row["topic_id"]),
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
        }
        for row in rows
    ]
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
        return []
    if not row:
        return []
    try:
        return _parse_json_list(row["topic_ids_json"])
    except Exception:
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
    conn.executemany(
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
        params,
    )


def _build_topic_search_sql(*, recent_cutoff: str | None = None) -> str:
    cutoff_clause = "AND t.create_time >= ?" if recent_cutoff else ""
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
          {cutoff_clause}
        ORDER BY t.create_time DESC
        LIMIT ?
    """.format(cutoff_clause=cutoff_clause)


def _build_question_topic_search_sql(keyword_count: int, *, recent_cutoff: str | None = None) -> str:
    cutoff_clause = "AND t.create_time >= ?" if recent_cutoff else ""
    conditions = " OR ".join(
        "(t.title ILIKE ? OR tk.text ILIKE ? OR q.text ILIKE ? OR a.text ILIKE ?)"
        for _ in range(keyword_count)
    )
    return f"""
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
          AND ({conditions})
          {cutoff_clause}
        ORDER BY t.create_time DESC
        LIMIT ?
    """.format(conditions=conditions, cutoff_clause=cutoff_clause)


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
    processed_topic_status: str = "analyzed",
    extract_mode: str = "",
) -> None:
    topic_ids = list(analyzed_topic_ids) if analyzed_topic_ids is not None else _topic_ids_from_result(result)
    _upsert_stock_topic_processed_states(
        conn,
        group_id=result["group_id"],
        stock_name=result["stock_name"],
        topic_ids=topic_ids,
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
        topic_ids = _parse_json_list(row["topic_ids_json"])
        try:
            topics = _load_topic_summaries(conn, _normalize_text(row["group_id"]), topic_ids)
        except Exception:
            topics = [_empty_topic_summary(topic_id) for topic_id in topic_ids]
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
            (like, group_id_text, like, like, like, like, recent_cutoff, MAX_SEARCH_CANDIDATE_TOPICS),
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
            processed_topic_ids.append(topic_id)
            topic_body = "\n".join(
                part for part in (row["talk_text"], row["question_text"], row["answer_text"]) if _normalize_text(part)
            )
            extracted_content, mode, matched_terms = _extract_relevant_topic_content(
                row["title"],
                topic_body,
                alias_terms,
            )
            if not extracted_content and _normalize_text(row["stock_name"]):
                extracted_content = "\n".join(
                    part
                    for part in (row["title"], topic_body, row["reason"])
                    if _normalize_text(part)
                )
                mode = "extraction_full"
                matched_terms = [_normalize_text(row["stock_name"])]
            if not extracted_content:
                continue
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
    topic_ids = [str(topic.get("topic_id") or "") for topic in search_result.get("topics", [])]
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

    topic_map = {str(topic.get("topic_id")): topic for topic in search_result.get("topics", [])}
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
            "concepts": list(topic_map.get(str(row["topic_id"]), {}).get("concepts") or []),
            "content": _clip(
                _normalize_text(topic_map.get(str(row["topic_id"]), {}).get("analysis_content")) or _topic_content(row),
                MAX_TOPIC_TEXT_CHARS,
            ),
        }
        for row in rows
    ]


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

    keywords = list(search_result.get("keywords") or [])
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
            "matched_keywords": [
                keyword
                for keyword in keywords
                if keyword.lower() in _topic_content(row).lower()
            ],
            "content": _clip(_topic_content(row), MAX_TOPIC_TEXT_CHARS),
        }
        for row in rows
    ]


def _build_stock_analysis_prompt(
    search_result: Dict[str, Any],
    topics: List[Dict[str, Any]],
    *,
    existing_summary: str = "",
) -> str:
    payload = {
        "group_id": search_result["group_id"],
        "stock_name": search_result["stock_name"],
        "stock_code": search_result.get("stock_code") or "",
        "market": search_result.get("market") or "",
        "recommendation_count": search_result.get("recommendation_count") or 0,
        "concepts": search_result.get("concepts") or [],
        "existing_summary_markdown": existing_summary,
        "new_topic_count": len(topics),
        "new_topics": topics,
    }
    return _clip(json.dumps(payload, ensure_ascii=False, indent=2), MAX_ANALYSIS_PROMPT_CHARS)


def _build_question_analysis_prompt(search_result: Dict[str, Any], topics: List[Dict[str, Any]]) -> str:
    payload = {
        "group_id": search_result["group_id"],
        "question": search_result["question"],
        "keywords": search_result.get("keywords") or [],
        "topic_count": len(topics),
        "topics": topics,
    }
    return _clip(json.dumps(payload, ensure_ascii=False, indent=2), MAX_ANALYSIS_PROMPT_CHARS)


def _call_stock_analysis_ai(prompt_payload: str, *, incremental: bool = False) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    wire_api = _normalize_text(runtime_ai_config.get("wire_api")) or get_default_wire_api()
    reasoning_effort = get_summary_reasoning_effort()
    user_prompt = (
        "请基于输入话题，对这只股票生成中文 Markdown 公司调研报告。\n\n"
        "结构：\n"
        "## 公司调研报告\n"
        "### 1. 投资摘要\n"
        "用 3-5 条概括当前最重要的结论，突出最值得关注的变化和判断。\n\n"
        "### 2. 公司定位与核心业务\n"
        "总结公司所处产业链位置、主要产品/服务、客户或下游方向。只使用输入话题中的信息。\n\n"
        "### 3. 核心逻辑与成长驱动\n"
        "总结卖方/调研材料中反复出现的主线，例如需求增长、国产替代、技术升级、产能释放、订单变化、价格变化等。\n\n"
        "### 4. 关键数据与预测\n"
        "整理话题中出现的收入、利润、订单、产能、出货量、目标价、市值空间等数字；没有明确数值时写未提及。\n\n"
        "### 5. 催化事件\n"
        "总结近期或未来可能影响公司认知变化的事件，包括新品、订单、客户、政策、行业景气、财报节点等。\n\n"
        "### 6. 后续跟踪要点\n"
        "列出后续需要继续跟踪的变量，例如订单兑现、毛利率、产能、客户导入、财报验证、行业价格等。\n\n"
        "### 7. 结论\n"
        "用 1-2 段收束当前报告，概括整体判断和最重要的后续观察点。\n"
        "要求：\n"
        "- 这是卖方调研社群材料，请按专业公司研究报告的风格输出，突出公司研究主线、催化、估值与跟踪点。\n"
        "- 只基于输入话题内容，不要补充外部行情、财报或未出现的信息。\n"
        "- 重点提炼可用于后续跟踪的结论、驱动因素、数据变化和事件进展。\n"
        "- 如果输入中出现数字或预测值，请在“关键数据与预测”中整理；没有明确数值时直接写未提及。\n"
        "- 如果输入中包含 existing_summary_markdown，请把新增话题自然融合进对应章节，并输出更新后的完整报告，不要只输出差异或单独列新章节。\n"
        "- 如果输入中出现新的观点或更新，只将其合并进对应章节，不要做流水账。\n"
        f"输入数据：\n{prompt_payload}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股卖方调研材料分析助手。"
                "只基于用户提供的知识星球话题内容生成专业公司调研报告，不要补充外部行情或未出现的信息。"
            ),
        },
        {
            "role": "user",
            "content": user_prompt,
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


def _extract_json_object(text: str) -> Dict[str, Any]:
    value = _normalize_text(text)
    try:
        parsed = json.loads(value)
    except Exception:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(value[start : end + 1])
        except Exception:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _call_question_keyword_ai(question: str) -> Tuple[List[str], str]:
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
                "你是A股社群话题检索助手。"
                "你的任务是把用户问题改写成适合数据库全文模糊搜索的中文关键词。"
                "只输出 JSON，不要 Markdown，不要解释。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请从用户问题中提取 1-6 个检索关键词。\n"
                "要求：\n"
                "- 优先保留行业、概念、股票简称、公司名、事件名。\n"
                "- 去掉“最近怎么样”“推荐吗”“怎么看”等提问语气。\n"
                "- 关键词要短，适合 ILIKE 模糊搜索，例如“商业航天板块最近怎么样，推荐吗”应输出“商业航天”。\n"
                "- 只输出 JSON：{\"keywords\":[\"关键词1\",\"关键词2\"]}\n\n"
                f"用户问题：{question}"
            ),
        },
    ]

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=120)
    if wire_api.strip().lower() == "responses":
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
        )
        text = _extract_response_text(response)
    else:
        response = client.chat.completions.create(model=model, messages=messages, stream=False)
        text = _normalize_text(response.choices[0].message.content)

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
    wire_api = _normalize_text(runtime_ai_config.get("wire_api")) or get_default_wire_api()
    reasoning_effort = get_summary_reasoning_effort()
    messages = [
        {
            "role": "system",
            "content": (
                "你是A股社群问答助手。"
                "只基于用户提供的知识星球话题内容回答，不要补充外部行情、新闻或未出现的信息。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                "请基于输入话题生成中文 Markdown 回答。\n\n"
                "结构：\n"
                "## 直接回答\n"
                "## 证据摘要\n"
                "## 分歧与不确定性\n"
                "## 相关话题索引\n\n"
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


def extract_stock_names_from_image(image_data_url: str) -> Dict[str, Any]:
    mime_type, normalized_data_url, image_bytes = _parse_image_data_url(image_data_url)
    runtime_ai_config = get_openai_compatible_config()
    api_key = _normalize_text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = _normalize_text(runtime_ai_config.get("model")) or get_default_model()
    api_base = _normalize_text(runtime_ai_config.get("base_url")) or get_default_base_url()
    wire_api = _normalize_text(runtime_ai_config.get("wire_api")) or get_default_wire_api()
    reasoning_effort = get_summary_reasoning_effort()
    prompt = (
        "请从这张图片中提取出现的 A 股股票名称。"
        "只输出 JSON，不要 Markdown，不要解释。"
        "如果识别到股票，JSON 结构为 {\"stockNames\": [\"股票名1\", \"股票名2\"]}。"
        "如果图片中没有明确股票名称，JSON 结构为 {\"error\": \"NO_STOCKS\"}。"
        "要求：保留图片里的股票中文简称，去重，最多 20 个。"
    )

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=120)
    if wire_api.strip().lower() == "responses":
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": normalized_data_url},
                    ],
                }
            ],
            reasoning={"effort": reasoning_effort},
        )
        text = _extract_response_text(response)
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": normalized_data_url}},
                    ],
                }
            ],
            stream=False,
        )
        text = _normalize_text(response.choices[0].message.content)

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
    processed_topic_ids = _merge_topic_ids(saved_topic_ids, search_result.get("processed_topic_ids") or current_topic_ids)
    new_topic_ids = [topic_id for topic_id in current_topic_ids if topic_id not in _topic_id_set(saved_topic_ids)]
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
        for batch_index, topic_batch in enumerate(topic_batches, start=1):
            _log(log_callback, f"🤖 AI 分析批次 {batch_index}/{len(topic_batches)}，话题 {len(topic_batch)} 条")
            summary, model = _call_stock_analysis_ai(
                _build_stock_analysis_prompt(
                    search_result,
                    topic_batch,
                    existing_summary=summary,
                ),
                incremental=bool(summary),
            )
            processed_topic_ids = _merge_topic_ids(processed_topic_ids, (topic.get("topic_id") for topic in topic_batch))
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
                    processed_topic_status="analyzed",
                )
            finally:
                conn.close()
    except Exception as exc:
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
            processed_topic_status="analyzed",
        )
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
    _log(log_callback, f"开始批量分析，共 {total} 只股票")

    for index, stock_name in enumerate(names, start=1):
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
            results.append(result)
            if result.get("topic_count", 0) <= 0:
                no_topic_count += 1
            else:
                success_count += 1
            _log(log_callback, f"{index}/{total} {result.get('stock_name') or stock_name}: 完成并保存")
        except Exception as exc:
            failed_count += 1
            latest = get_latest_stock_topic_analysis(group_id_text, stock_name) or _empty_latest_result(group_id_text, stock_name)
            failed_result = {
                **latest,
                "status": "failed",
                "error": str(exc),
            }
            results.append(failed_result)
            _log(log_callback, f"{index}/{total} {stock_name}: 失败 - {str(exc)}")

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
