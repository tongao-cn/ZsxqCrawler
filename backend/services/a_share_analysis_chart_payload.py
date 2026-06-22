from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.services.a_share_analysis_chart import (
    DEFAULT_RANKING_TOP_N,
    DEFAULT_RANKING_WINDOWS,
    attach_rank_movement,
    build_coverage_pool,
    build_ranking_rows,
    color_for_name,
)
from backend.services.a_share_analysis_dates import select_available_date_range
from backend.services.a_share_analysis_local_store import normalize_group_id


def empty_chart_payload(
    group_id: Optional[str],
    available_dates: Sequence[str],
    selected_start_date: Optional[str],
    selected_end_date: Optional[str],
    top_n: int,
    ranking_top_n: int,
) -> Dict[str, Any]:
    return {
        "group_id": normalize_group_id(group_id),
        "available_dates": list(available_dates),
        "selected_start_date": selected_start_date,
        "selected_end_date": selected_end_date,
        "chart_data": [],
        "series": [],
        "rankings": {},
        "coverage_pool": [],
        "date_count": 0,
        "company_count": 0,
        "total_companies_in_range": 0,
        "top_n": top_n,
        "ranking_top_n": ranking_top_n,
    }


def build_chart_payload_from_daily(
    daily: Mapping[str, Mapping[str, int]],
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    top_n: int = 20,
    ranking_windows: Sequence[int] = DEFAULT_RANKING_WINDOWS,
    ranking_top_n: int = DEFAULT_RANKING_TOP_N,
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    available_dates = sorted(daily.keys())
    if not available_dates:
        return empty_chart_payload(
            normalize_group_id(group_id),
            [],
            None,
            None,
            top_n,
            ranking_top_n,
        )

    selected_start, selected_end, range_dates = select_available_date_range(available_dates, start_date, end_date)
    if not range_dates:
        return empty_chart_payload(
            group_id,
            available_dates,
            selected_start,
            selected_end,
            top_n,
            ranking_top_n,
        )

    company_totals: Dict[str, int] = defaultdict(int)
    for day in range_dates:
        for company, count in daily.get(day, {}).items():
            company_totals[company] += count

    top_companies = sorted(company_totals.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    selected_companies = [company for company, _count in top_companies]
    cumulative = {company: 0 for company in selected_companies}
    chart_data: List[Dict[str, Any]] = []
    for day in range_dates:
        row: Dict[str, Any] = {"date": day}
        for company in selected_companies:
            cumulative[company] += daily.get(day, {}).get(company, 0)
            row[company] = cumulative[company]
        chart_data.append(row)

    series = [
        {
            "key": company,
            "label": company,
            "total": total,
            "color": color_for_name(company),
        }
        for company, total in top_companies
    ]

    rankings: Dict[str, List[Dict[str, Any]]] = {}
    start_index = available_dates.index(range_dates[0])
    end_index = available_dates.index(range_dates[-1])
    for window in ranking_windows:
        from_index = max(start_index, end_index - int(window) + 1)
        current_rows = build_ranking_rows(daily, available_dates, from_index, end_index, ranking_top_n)

        previous_rows: List[Dict[str, Any]] = []
        previous_end_index = end_index - 1
        if previous_end_index >= start_index:
            previous_from_index = max(start_index, previous_end_index - int(window) + 1)
            previous_rows = build_ranking_rows(
                daily,
                available_dates,
                previous_from_index,
                previous_end_index,
                ranking_top_n,
            )

        rankings[str(window)] = attach_rank_movement(current_rows, previous_rows)

    coverage_pool = build_coverage_pool(daily, available_dates, start_index, end_index)

    return {
        "group_id": normalize_group_id(group_id),
        "available_dates": available_dates,
        "selected_start_date": range_dates[0],
        "selected_end_date": range_dates[-1],
        "chart_data": chart_data,
        "series": series,
        "rankings": rankings,
        "coverage_pool": coverage_pool,
        "date_count": len(range_dates),
        "company_count": len(selected_companies),
        "total_companies_in_range": len(company_totals),
        "top_n": top_n,
        "ranking_top_n": ranking_top_n,
    }
