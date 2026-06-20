"""Read-only external stock summary aggregation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.services.stock_external_summary_store import RECOMMENDATION_WINDOWS, load_external_stock_summary_sources
from backend.services.stock_topic_analysis_service import parse_stock_names


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


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _normalize_text(value)
        if text:
            return text
    return ""


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
    source_data = load_external_stock_summary_sources(group_id_text, names, report_date=report_date_text)
    stocks_by_name = source_data.get("stocks", {})
    stocks = []
    for stock_name in names:
        sources = stocks_by_name.get(stock_name, {})
        stocks.append(
            _build_stock_summary(
                input_name=stock_name,
                daily_concept=sources.get("daily_concept"),
                topic_analysis=sources.get("topic_analysis"),
                recent_topic_evidence=sources.get("recent_topic_evidence") or [],
                recommendation_counts=sources.get("recommendation_counts") or {},
            )
        )
    return {
        "group_id": source_data.get("group_id", group_id_text),
        "report_date": source_data.get("report_date", report_date_text),
        "stocks": stocks,
    }


__all__ = ["get_external_stock_summaries"]
