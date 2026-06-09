from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


DEFAULT_RANKING_WINDOWS = (30,)
DEFAULT_RANKING_TOP_N = 100
DEFAULT_COVERAGE_PRIMARY_WINDOW = 30
DEFAULT_COVERAGE_PRIMARY_TOP_N = 300
DEFAULT_COVERAGE_SHORT_WINDOWS = ((7, 100), (14, 150))


def color_for_name(name: str) -> str:
    seed = sum((index + 1) * ord(char) for index, char in enumerate(name))
    hue = seed % 360
    saturation = 58 + (seed % 17)
    lightness = 45 + (seed % 10)
    return f"hsl({hue}, {saturation}%, {lightness}%)"


def build_ranking_rows(
    daily: Mapping[str, Mapping[str, int]],
    available_dates: Sequence[str],
    from_index: int,
    end_index: int,
    ranking_top_n: int,
) -> List[Dict[str, Any]]:
    totals: Dict[str, int] = defaultdict(int)
    for index in range(from_index, end_index + 1):
        day = available_dates[index]
        for company, count in daily.get(day, {}).items():
            totals[company] += count

    return [
        {"company": company, "count": count, "rank": rank}
        for rank, (company, count) in enumerate(
            sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:ranking_top_n],
            start=1,
        )
    ]


def attach_rank_movement(
    current_rows: List[Dict[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    previous_ranks = {
        str(row.get("company") or ""): int(row.get("rank") or 0)
        for row in previous_rows
        if str(row.get("company") or "").strip() and int(row.get("rank") or 0) > 0
    }

    enriched_rows: List[Dict[str, Any]] = []
    for row in current_rows:
        company = str(row.get("company") or "")
        rank = int(row.get("rank") or 0)
        previous_rank = previous_ranks.get(company)
        if previous_rank is None:
            rank_change = None
            trend = "new"
        else:
            rank_change = previous_rank - rank
            if rank_change > 0:
                trend = "up"
            elif rank_change < 0:
                trend = "down"
            else:
                trend = "flat"

        enriched_rows.append(
            {
                **row,
                "previous_rank": previous_rank,
                "rank_change": rank_change,
                "trend": trend,
            }
        )
    return enriched_rows


def coverage_layer(rank_30: Optional[int]) -> Tuple[str, str, int]:
    if rank_30 is None:
        return "short_active", "短周期补充", 5
    if rank_30 <= 50:
        return "core", "核心1-50", 1
    if rank_30 <= 100:
        return "main", "主池51-100", 2
    if rank_30 <= 200:
        return "extended", "扩展101-200", 3
    return "long_tail", "长尾201-300", 4


def build_coverage_pool(
    daily: Mapping[str, Mapping[str, int]],
    available_dates: Sequence[str],
    start_index: int,
    end_index: int,
) -> List[Dict[str, Any]]:
    rows_by_window: Dict[int, List[Dict[str, Any]]] = {}
    for window, top_n in (
        (DEFAULT_COVERAGE_PRIMARY_WINDOW, DEFAULT_COVERAGE_PRIMARY_TOP_N),
        *DEFAULT_COVERAGE_SHORT_WINDOWS,
    ):
        from_index = max(start_index, end_index - int(window) + 1)
        rows_by_window[window] = build_ranking_rows(daily, available_dates, from_index, end_index, top_n)

    previous_primary_rows: List[Dict[str, Any]] = []
    previous_end_index = end_index - 1
    if previous_end_index >= start_index:
        previous_from_index = max(start_index, previous_end_index - DEFAULT_COVERAGE_PRIMARY_WINDOW + 1)
        previous_primary_rows = build_ranking_rows(
            daily,
            available_dates,
            previous_from_index,
            previous_end_index,
            DEFAULT_COVERAGE_PRIMARY_TOP_N,
        )

    primary_rows = attach_rank_movement(rows_by_window[DEFAULT_COVERAGE_PRIMARY_WINDOW], previous_primary_rows)
    items_by_company: Dict[str, Dict[str, Any]] = {}

    for row in primary_rows:
        company = str(row.get("company") or "")
        rank_30 = int(row.get("rank") or 0)
        layer, layer_label, layer_order = coverage_layer(rank_30)
        items_by_company[company] = {
            "company": company,
            "layer": layer,
            "layer_label": layer_label,
            "layer_order": layer_order,
            "rank_30": rank_30,
            "count_30": int(row.get("count") or 0),
            "previous_rank_30": row.get("previous_rank"),
            "rank_change_30": row.get("rank_change"),
            "trend_30": row.get("trend"),
            "rank_7": None,
            "count_7": None,
            "rank_14": None,
            "count_14": None,
            "tags": [],
        }

    for window, _top_n in DEFAULT_COVERAGE_SHORT_WINDOWS:
        for row in rows_by_window[window]:
            company = str(row.get("company") or "")
            item = items_by_company.setdefault(
                company,
                {
                    "company": company,
                    "rank_30": None,
                    "count_30": None,
                    "previous_rank_30": None,
                    "rank_change_30": None,
                    "trend_30": None,
                    "rank_7": None,
                    "count_7": None,
                    "rank_14": None,
                    "count_14": None,
                    "tags": [],
                },
            )
            item[f"rank_{window}"] = int(row.get("rank") or 0)
            item[f"count_{window}"] = int(row.get("count") or 0)

    for item in items_by_company.values():
        rank_30 = item.get("rank_30")
        layer, layer_label, layer_order = coverage_layer(rank_30 if isinstance(rank_30, int) else None)
        item["layer"] = item.get("layer") or layer
        item["layer_label"] = item.get("layer_label") or layer_label
        item["layer_order"] = item.get("layer_order") or layer_order
        tags: List[str] = []
        if item.get("rank_7") and (not item.get("rank_30") or int(item["rank_30"]) > 100):
            tags.append("7日新进")
        if item.get("rank_14") and (not item.get("rank_30") or int(item["rank_30"]) > 100):
            tags.append("14日活跃")
        if item.get("trend_30") == "up":
            tags.append("30日上升")
        if item.get("trend_30") == "down":
            tags.append("30日下降")
        item["tags"] = tags

    return sorted(
        items_by_company.values(),
        key=lambda item: (
            int(item.get("layer_order") or 99),
            int(item.get("rank_30") or 999999),
            int(item.get("rank_7") or 999999),
            int(item.get("rank_14") or 999999),
            str(item.get("company") or ""),
        ),
    )
