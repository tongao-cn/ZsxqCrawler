"""Persistence helpers for stock topic analysis."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Iterable, List

from backend.services.daily_topic_analysis_topics import clip_text as _clip
from backend.services.stock_topic_analysis_helpers import _build_stock_alias_terms
from backend.services.stock_topic_analysis_payloads import require_topic_excerpt
from backend.services.stock_topic_analysis_queries import build_question_topic_search_sql, build_topic_search_sql
from backend.storage.db_compat import connect


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


def parse_json_list(value: Any) -> List[str]:
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


def serialize_json_list(values: Iterable[Any], *, max_tracked_topic_ids: int) -> str:
    return json.dumps(_ordered_unique(values, limit=max_tracked_topic_ids), ensure_ascii=False)


def question_topic_rows_query(group_id: str, topic_ids: List[str]) -> tuple[str, List[Any]]:
    placeholders = ",".join("?" for _ in topic_ids)
    return (
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
        [_normalize_text(group_id), *topic_ids],
    )


def question_topic_search_query(
    group_id: str,
    keywords: List[str],
    *,
    recent_cutoff: str,
    limit: int,
) -> tuple[str, List[Any]]:
    params: List[Any] = [_normalize_text(group_id)]
    for keyword in keywords:
        like = f"%{keyword}%"
        params.extend([like, like, like, like])
    params.append(recent_cutoff)
    params.append(max(1, int(limit)))
    return build_question_topic_search_sql(len(keywords), recent_cutoff=recent_cutoff), params


def load_question_topic_rows(group_id: str, topic_ids: Iterable[Any]) -> List[Any]:
    normalized_topic_ids = [str(topic_id or "") for topic_id in topic_ids]
    if not normalized_topic_ids:
        return []

    conn = connect()
    try:
        sql, params = question_topic_rows_query(_normalize_text(group_id), normalized_topic_ids)
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def load_question_topic_search_rows(
    group_id: str,
    keywords: Iterable[str],
    *,
    recent_cutoff: str,
    limit: int,
) -> List[Any]:
    normalized_keywords = [_normalize_text(keyword) for keyword in keywords]
    if not normalized_keywords:
        return []

    conn = connect()
    try:
        sql, params = question_topic_search_query(
            _normalize_text(group_id),
            normalized_keywords,
            recent_cutoff=recent_cutoff,
            limit=limit,
        )
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def load_stock_topic_search_rows(
    conn: Any,
    group_id: str,
    search_term: str,
    *,
    recent_cutoff: str,
    max_candidate_topics: int,
) -> List[Any]:
    return conn.execute(
        build_topic_search_sql(recent_cutoff=recent_cutoff),
        (
            f"%{search_term}%",
            _normalize_text(group_id),
            recent_cutoff,
            max(1, int(max_candidate_topics)),
        ),
    ).fetchall()


def _load_topic_excerpt_fallbacks(conn: Any, group_id: str, topic_ids: List[str], stock_name: str) -> Dict[str, str]:
    alias_terms = _build_stock_alias_terms(stock_name)
    if not topic_ids or not alias_terms:
        return {}
    topic_placeholders = ",".join("?" for _ in topic_ids)
    alias_conditions = " OR ".join("stock_name ILIKE ?" for _ in alias_terms)
    rows = conn.execute(
        f"""
        SELECT topic_id, excerpt
        FROM zsxq_a_share_topic_stock_extractions
        WHERE group_id = ?
          AND topic_id IN ({topic_placeholders})
          AND COALESCE(TRIM(excerpt), '') <> ''
          AND ({alias_conditions})
        ORDER BY topic_date DESC, topic_id DESC
        """,
        [group_id, *topic_ids, *(f"%{term}%" for term in alias_terms)],
    ).fetchall()
    excerpts: Dict[str, str] = {}
    for row in rows:
        topic_id = str(row["topic_id"])
        if topic_id not in excerpts:
            excerpts[topic_id] = _normalize_text(row["excerpt"])
    return excerpts


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


def load_saved_topic_summaries(conn: Any, group_id: str, topic_ids: List[str], stock_name: str = "") -> List[Dict[str, Any]]:
    if not topic_ids:
        return []
    fallback_excerpts = _load_topic_excerpt_fallbacks(conn, group_id, topic_ids, stock_name)
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
         AND e.stock_name = ?
        WHERE t.group_id::text = ?
          AND t.topic_id::text IN ({placeholders})
        ORDER BY t.create_time DESC
        """,
        [_normalize_text(stock_name), group_id, *topic_ids],
    ).fetchall()
    summaries: List[Dict[str, Any]] = []
    for row in rows:
        topic_id = str(row["topic_id"])
        excerpt = require_topic_excerpt(
            row["excerpt"] or fallback_excerpts.get(topic_id),
            topic_id=topic_id,
            stock_name=stock_name,
        )
        summaries.append(
            {
                "topic_id": topic_id,
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
    found = {item["topic_id"] for item in summaries}
    summaries.extend(_empty_topic_summary(topic_id) for topic_id in topic_ids if str(topic_id) not in found)
    return summaries


def load_saved_stock_topic_analysis(group_id: str, stock_name: str) -> Dict[str, Any] | None:
    query = _normalize_text(stock_name)
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT group_id, stock_name, stock_code, market, topic_ids_json,
                   concepts_json, recommendation_count, summary_markdown,
                   model, status, error, created_at, updated_at
            FROM stock_topic_analyses
            WHERE group_id = ?
              AND stock_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_normalize_text(group_id), query),
        ).fetchone()
        if not row:
            return None
        topic_ids = parse_json_list(row["topic_ids_json"])
        topics = load_saved_topic_summaries(conn, _normalize_text(row["group_id"]), topic_ids, row["stock_name"])
        return {
            "group_id": row["group_id"],
            "stock_name": row["stock_name"],
            "stock_code": row["stock_code"] or "",
            "market": row["market"] or "",
            "topics": topics,
            "concepts": parse_json_list(row["concepts_json"]),
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


def load_stock_topic_processed_state_ids(
    conn: Any,
    group_id: str,
    stock_name: str,
    *,
    processed_topic_statuses: set[str],
    max_tracked_topic_ids: int,
) -> List[str]:
    placeholders = ",".join("?" for _ in processed_topic_statuses)
    try:
        rows = conn.execute(
            f"""
            SELECT topic_id
            FROM stock_topic_processed_states
            WHERE group_id = ?
              AND stock_name = ?
              AND status IN ({placeholders})
            ORDER BY updated_at ASC
            """,
            [
                _normalize_text(group_id),
                _normalize_text(stock_name),
                *sorted(processed_topic_statuses),
            ],
        ).fetchall()
    except Exception:
        conn.rollback()
        return []
    return _ordered_unique((row["topic_id"] for row in rows), limit=max_tracked_topic_ids)


def load_latest_processed_topic_ids(
    conn: Any,
    group_id: str,
    stock_name: str,
    *,
    processed_topic_statuses: set[str],
    max_tracked_topic_ids: int,
) -> List[str]:
    query = _normalize_text(stock_name)
    if not query:
        return []
    state_ids = load_stock_topic_processed_state_ids(
        conn,
        group_id,
        query,
        processed_topic_statuses=processed_topic_statuses,
        max_tracked_topic_ids=max_tracked_topic_ids,
    )
    if state_ids:
        return state_ids
    try:
        row = conn.execute(
            """
            SELECT topic_ids_json
            FROM stock_topic_analyses
            WHERE group_id = ?
              AND stock_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_normalize_text(group_id), query),
        ).fetchone()
    except Exception:
        conn.rollback()
        return []
    if not row:
        return []
    try:
        return parse_json_list(row["topic_ids_json"])
    except Exception:
        conn.rollback()
        return []


def upsert_stock_topic_processed_states(
    conn: Any,
    *,
    group_id: str,
    stock_name: str,
    topic_ids: Iterable[Any],
    status: str,
    max_tracked_topic_ids: int,
    extract_mode: str = "",
    model: str = "",
    error: str = "",
) -> None:
    normalized_topic_ids = _ordered_unique(topic_ids, limit=max_tracked_topic_ids)
    if not normalized_topic_ids:
        return
    params = [
        (
            _normalize_text(group_id),
            _normalize_text(stock_name),
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


def upsert_stock_topic_analysis(
    conn: Any,
    *,
    result: Dict[str, Any],
    status: str,
    topic_ids: List[Any],
    max_tracked_topic_ids: int,
    error: str = "",
    processed_state_topic_ids: Iterable[Any] | None = None,
    processed_topic_status: str = "analyzed",
    extract_mode: str = "",
    write_processed_state: bool = True,
    commit: bool = True,
) -> None:
    if write_processed_state:
        state_topic_ids = list(processed_state_topic_ids) if processed_state_topic_ids is not None else topic_ids
        upsert_stock_topic_processed_states(
            conn,
            group_id=result["group_id"],
            stock_name=result["stock_name"],
            topic_ids=state_topic_ids,
            status=processed_topic_status,
            max_tracked_topic_ids=max_tracked_topic_ids,
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
            serialize_json_list(topic_ids, max_tracked_topic_ids=max_tracked_topic_ids),
            serialize_json_list(result.get("concepts", []), max_tracked_topic_ids=max_tracked_topic_ids),
            int(result.get("recommendation_count") or 0),
            result.get("summary_markdown", ""),
            result.get("model", ""),
            status,
            error,
        ),
    )
    if commit:
        conn.commit()


def insert_stock_topic_analysis_version(
    conn: Any,
    *,
    result: Dict[str, Any],
    status: str,
    topic_ids: List[Any],
    max_tracked_topic_ids: int,
    error: str = "",
) -> None:
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
            serialize_json_list(topic_ids, max_tracked_topic_ids=max_tracked_topic_ids),
            serialize_json_list(result.get("concepts", []), max_tracked_topic_ids=max_tracked_topic_ids),
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
