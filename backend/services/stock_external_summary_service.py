"""Read-only external stock summary aggregation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

from backend.services.stock_topic_analysis_service import parse_stock_names
from backend.services.stock_topic_analysis_store import parse_json_list
from backend.storage.db_compat import connect


RECENT_EVIDENCE_LIMIT = 5
RECOMMENDATION_WINDOWS = (7, 14, 30)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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


def _stock_query_params(group_id: str, stock_name: str) -> List[Any]:
    query = _normalize_text(stock_name)
    return [_normalize_text(group_id), f"%{query}%", query]


def _load_latest_daily_concept(
    conn: Any,
    *,
    group_id: str,
    stock_name: str,
    report_date: Optional[str] = None,
) -> Dict[str, Any] | None:
    date_filter = "AND report_date = ?" if report_date else ""
    params = _stock_query_params(group_id, stock_name)
    if report_date:
        params.append(_normalize_text(report_date))
    row = conn.execute(
        f"""
        SELECT report_date, stock_name, stock_code, market, concepts_json,
               reason, topic_ids_json, confidence, model, status, error, updated_at
        FROM daily_stock_concepts
        WHERE group_id = ?
          AND stock_name <> ''
          AND (stock_name ILIKE ? OR stock_code = ?)
          {date_filter}
        ORDER BY report_date DESC, confidence DESC, updated_at DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if not row:
        return None
    return {
        "report_date": row["report_date"] or "",
        "stock_name": row["stock_name"] or "",
        "stock_code": row["stock_code"] or "",
        "market": row["market"] or "",
        "concepts": parse_json_list(row["concepts_json"]),
        "reason": row["reason"] or "",
        "topic_ids": parse_json_list(row["topic_ids_json"]),
        "confidence": float(row["confidence"] or 0),
        "model": row["model"] or "",
        "status": row["status"] or "",
        "error": row["error"] or "",
        "updated_at": row["updated_at"],
    }


def _load_latest_topic_analysis(conn: Any, *, group_id: str, stock_name: str) -> Dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT stock_name, stock_code, market, topic_ids_json, concepts_json,
               recommendation_count, summary_markdown, model, status, error,
               created_at, updated_at
        FROM stock_topic_analyses
        WHERE group_id = ?
          AND (stock_name ILIKE ? OR stock_code = ?)
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        _stock_query_params(group_id, stock_name),
    ).fetchone()
    if not row:
        return None
    topic_ids = parse_json_list(row["topic_ids_json"])
    return {
        "stock_name": row["stock_name"] or "",
        "stock_code": row["stock_code"] or "",
        "market": row["market"] or "",
        "concepts": parse_json_list(row["concepts_json"]),
        "topic_ids": topic_ids,
        "topic_count": len(topic_ids),
        "recommendation_count": int(row["recommendation_count"] or 0),
        "summary_markdown": row["summary_markdown"] or "",
        "model": row["model"] or "",
        "status": row["status"] or "",
        "error": row["error"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _load_recent_topic_evidence(conn: Any, *, group_id: str, stock_name: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT topic_date::text AS topic_date, topic_id, stock_name, stock_code,
               market, concepts_json, excerpt, reason, confidence, model, updated_at
        FROM zsxq_a_share_topic_stock_extractions
        WHERE group_id = ?
          AND (stock_name ILIKE ? OR stock_code = ?)
        ORDER BY topic_date DESC, confidence DESC, updated_at DESC
        LIMIT ?
        """,
        [*_stock_query_params(group_id, stock_name), RECENT_EVIDENCE_LIMIT],
    ).fetchall()
    return [
        {
            "topic_date": row["topic_date"] or "",
            "topic_id": str(row["topic_id"] or ""),
            "stock_name": row["stock_name"] or "",
            "stock_code": row["stock_code"] or "",
            "market": row["market"] or "",
            "concepts": parse_json_list(row["concepts_json"]),
            "excerpt": row["excerpt"] or "",
            "reason": row["reason"] or "",
            "confidence": float(row["confidence"] or 0),
            "model": row["model"] or "",
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _normalize_text(value)
        if text:
            return text
    return ""


def _parse_iso_date(value: Any) -> date | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _load_latest_recommendation_date(conn: Any, *, group_id: str) -> str:
    row = conn.execute(
        """
        SELECT MAX(mention_date)::text AS latest_date
        FROM zsxq_a_share_daily_mentions
        WHERE group_id = ?
        """,
        (_normalize_text(group_id),),
    ).fetchone()
    return _normalize_text(row["latest_date"] if row else "")


def _load_recommendation_counts(
    conn: Any,
    *,
    group_id: str,
    stock_names: Iterable[Any],
    as_of_date: str,
) -> Dict[str, Any]:
    anchor = _parse_iso_date(as_of_date)
    names = _ordered_unique(stock_names, limit=10)
    counts = {f"{window}d": 0 for window in RECOMMENDATION_WINDOWS}
    if not anchor or not names:
        return {"as_of_date": as_of_date or "", **counts}

    company_conditions = " OR ".join("company ILIKE ?" for _ in names)
    for window in RECOMMENDATION_WINDOWS:
        start_date = anchor - timedelta(days=window - 1)
        params: List[Any] = [
            _normalize_text(group_id),
            start_date.isoformat(),
            anchor.isoformat(),
            *(f"%{name}%" for name in names),
        ]
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(mentions_count), 0) AS mention_count
            FROM zsxq_a_share_daily_mentions
            WHERE group_id = ?
              AND mention_date >= ?::date
              AND mention_date <= ?::date
              AND ({company_conditions})
            """,
            params,
        ).fetchone()
        counts[f"{window}d"] = int(row["mention_count"] or 0) if row else 0
    return {"as_of_date": anchor.isoformat(), **counts}


def _build_stock_summary(
    *,
    input_name: str,
    daily_concept: Dict[str, Any] | None,
    topic_analysis: Dict[str, Any] | None,
    recent_topic_evidence: List[Dict[str, Any]],
    recommendation_counts: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_concepts = [
        concept
        for evidence in recent_topic_evidence
        for concept in evidence.get("concepts", [])
    ]
    concepts = _ordered_unique(
        [
            *((daily_concept or {}).get("concepts") or []),
            *((topic_analysis or {}).get("concepts") or []),
            *evidence_concepts,
        ],
        limit=50,
    )
    stock_name = _first_non_empty(
        (topic_analysis or {}).get("stock_name"),
        (daily_concept or {}).get("stock_name"),
        (recent_topic_evidence[0] or {}).get("stock_name") if recent_topic_evidence else "",
        input_name,
    )
    stock_code = _first_non_empty(
        (topic_analysis or {}).get("stock_code"),
        (daily_concept or {}).get("stock_code"),
        (recent_topic_evidence[0] or {}).get("stock_code") if recent_topic_evidence else "",
    )
    market = _first_non_empty(
        (topic_analysis or {}).get("market"),
        (daily_concept or {}).get("market"),
        (recent_topic_evidence[0] or {}).get("market") if recent_topic_evidence else "",
    )
    summary_markdown = _normalize_text((topic_analysis or {}).get("summary_markdown"))
    has_recommendation_counts = any(
        int(recommendation_counts.get(f"{window}d") or 0) > 0
        for window in RECOMMENDATION_WINDOWS
    )
    return {
        "input": input_name,
        "stock_name": stock_name,
        "stock_code": stock_code,
        "market": market,
        "has_data": bool(
            concepts
            or summary_markdown
            or daily_concept
            or topic_analysis
            or recent_topic_evidence
            or has_recommendation_counts
        ),
        "concepts": concepts,
        "recommendation_counts": recommendation_counts,
        "recommendation_count_7d": int(recommendation_counts.get("7d") or 0),
        "recommendation_count_14d": int(recommendation_counts.get("14d") or 0),
        "recommendation_count_30d": int(recommendation_counts.get("30d") or 0),
        "summary_markdown": summary_markdown,
        "daily_concept": daily_concept,
        "stock_topic_analysis": topic_analysis,
        "recent_topic_evidence": recent_topic_evidence,
    }


def get_external_stock_summaries(
    group_id: str,
    stock_names: Any,
    *,
    report_date: Optional[str] = None,
) -> Dict[str, Any]:
    names = parse_stock_names(stock_names)
    if not names:
        raise ValueError("stock_names 不能为空")

    group_id_text = _normalize_text(group_id)
    report_date_text = _normalize_text(report_date) or None
    conn = connect()
    try:
        stocks = []
        recommendation_as_of_date = _load_latest_recommendation_date(conn, group_id=group_id_text)
        for stock_name in names:
            daily_concept = _load_latest_daily_concept(
                conn,
                group_id=group_id_text,
                stock_name=stock_name,
                report_date=report_date_text,
            )
            topic_analysis = _load_latest_topic_analysis(conn, group_id=group_id_text, stock_name=stock_name)
            recent_topic_evidence = _load_recent_topic_evidence(conn, group_id=group_id_text, stock_name=stock_name)
            recommendation_stock_names = [
                stock_name,
                (topic_analysis or {}).get("stock_name"),
                (daily_concept or {}).get("stock_name"),
                *((item.get("stock_name") for item in recent_topic_evidence)),
            ]
            recommendation_counts = _load_recommendation_counts(
                conn,
                group_id=group_id_text,
                stock_names=recommendation_stock_names,
                as_of_date=recommendation_as_of_date,
            )
            stocks.append(
                _build_stock_summary(
                    input_name=stock_name,
                    daily_concept=daily_concept,
                    topic_analysis=topic_analysis,
                    recent_topic_evidence=recent_topic_evidence,
                    recommendation_counts=recommendation_counts,
                )
            )
        return {
            "group_id": group_id_text,
            "report_date": report_date_text,
            "stocks": stocks,
        }
    finally:
        conn.close()


__all__ = ["get_external_stock_summaries"]
