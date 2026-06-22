"""Recommendation pool rotation backtest calculations."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.core.group_identity import normalize_group_id
from backend.services.a_share_signal_codes import resolve_signal_ts_code


DEFAULT_POOL_ROTATION_DAILY_FIELDS = [
    "group_id",
    "window_days",
    "signal_date",
    "entry_date",
    "exit_date",
    "pool_size",
    "resolved_count",
    "unresolved_count",
    "missing_quote_count",
    "portfolio_return",
    "status",
    "holdings_json",
]
DEFAULT_POOL_ROTATION_PERIOD_FIELDS = [
    "group_id",
    "window_days",
    "period_type",
    "period",
    "start_trade_date",
    "end_trade_date",
    "trading_days",
    "compound_return",
    "mean_daily_return",
    "win_rate",
]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _parse_day(value: Any, field_name: str) -> date:
    try:
        return datetime.strptime(_normalize_text(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def _validate_day(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    return _parse_day(value, field_name).isoformat()


def _is_tradable_quote(quote: Mapping[str, Any]) -> bool:
    return _safe_float(quote.get("close")) > 0 and (
        _safe_float(quote.get("amount")) > 0 or _safe_float(quote.get("vol")) > 0
    )


def _is_tradable_entry_quote(quote: Mapping[str, Any]) -> bool:
    return _is_tradable_quote(quote) and _safe_float(quote.get("open")) > 0


def _normalize_windows(windows: Sequence[int]) -> Tuple[int, ...]:
    normalized: List[int] = []
    for value in windows:
        try:
            window = int(value)
        except Exception:
            continue
        if window > 0 and window not in normalized:
            normalized.append(window)
    if not normalized:
        raise ValueError("推荐池窗口不能为空")
    return tuple(normalized)


def build_recommendation_pool_memberships(
    daily_mentions: Mapping[str, Mapping[str, int]],
    *,
    group_id: Any = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    windows: Sequence[int],
    ranking_top_n: int,
) -> List[Dict[str, Any]]:
    start_day = _validate_day(start_date, "start_date") or ""
    end_day = _validate_day(end_date, "end_date") or ""
    if start_day and end_day and start_day > end_day:
        raise ValueError("start_date 不能晚于 end_date")

    available_dates = sorted({_normalize_text(day) for day in daily_mentions.keys() if _normalize_text(day)})
    for day in available_dates:
        _parse_day(day, "mention_date")

    normalized_windows = _normalize_windows(windows)
    top_n = int(ranking_top_n or 0)
    rows: List[Dict[str, Any]] = []
    normalized_group_id = normalize_group_id(group_id) or _normalize_text(group_id)

    for end_index, signal_date in enumerate(available_dates):
        if start_day and signal_date < start_day:
            continue
        if end_day and signal_date > end_day:
            continue

        for window_days in normalized_windows:
            from_index = max(0, end_index - window_days + 1)
            totals: Dict[str, int] = defaultdict(int)
            for day in available_dates[from_index : end_index + 1]:
                for company, count in daily_mentions.get(day, {}).items():
                    stock_name = _normalize_text(company)
                    mention_count = _safe_int(count)
                    if stock_name and mention_count > 0:
                        totals[stock_name] += mention_count

            ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
            if top_n > 0:
                ranked = ranked[:top_n]
            for rank, (stock_name, mention_count) in enumerate(ranked, start=1):
                rows.append(
                    {
                        "group_id": normalized_group_id,
                        "window_days": window_days,
                        "signal_date": signal_date,
                        "rank": rank,
                        "stock_name": stock_name,
                        "mention_count": mention_count,
                    }
                )

    return rows


def pool_quote_range_bounds(membership_rows: Sequence[Mapping[str, Any]]) -> Tuple[date, date]:
    signal_dates = [_parse_day(row.get("signal_date"), "signal_date") for row in membership_rows if row.get("signal_date")]
    if not signal_dates:
        raise ValueError("没有可用于推荐池轮换收益的 signal_date")
    return min(signal_dates), max(signal_dates) + timedelta(days=10)


def _quotes_by_ts_code_and_day(quote_rows: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for raw in quote_rows:
        ts_code = _normalize_text(raw.get("ts_code")).upper()
        trade_date = _normalize_text(raw.get("trade_date"))
        if not ts_code or not trade_date:
            continue
        lookup[(ts_code, trade_date)] = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "open": _safe_float(raw.get("open")),
            "close": _safe_float(raw.get("close")),
            "vol": _safe_float(raw.get("vol")),
            "amount": _safe_float(raw.get("amount")),
        }
    return lookup


def _normalize_trade_dates(trade_dates: Iterable[Any]) -> List[str]:
    trade_dates = sorted({_normalize_text(value) for value in trade_dates if _normalize_text(value)})
    for trade_date in trade_dates:
        _parse_day(trade_date, "trade_date")
    return trade_dates


def rotation_entry_exit_dates(signal_date: str, trade_dates: Sequence[str]) -> Tuple[str, str]:
    entry_index = bisect_right(trade_dates, signal_date)
    if entry_index >= len(trade_dates):
        return "", ""
    exit_index = entry_index + 1
    if exit_index >= len(trade_dates):
        return trade_dates[entry_index], ""
    return trade_dates[entry_index], trade_dates[exit_index]


def build_pool_rotation_daily_rows(
    membership_rows: Iterable[Mapping[str, Any]],
    quote_rows: Iterable[Mapping[str, Any]],
    *,
    trade_dates: Iterable[Any] | None = None,
    stock_basic_index: Mapping[str, str] | None = None,
) -> List[Dict[str, Any]]:
    quote_list = list(quote_rows)
    quote_lookup = _quotes_by_ts_code_and_day(quote_list)
    normalized_trade_dates = _normalize_trade_dates(
        trade_dates if trade_dates is not None else [row.get("trade_date") for row in quote_list]
    )
    grouped_members: Dict[Tuple[str, int, str], List[Mapping[str, Any]]] = defaultdict(list)
    for member in membership_rows:
        group_id = _normalize_text(member.get("group_id"))
        window_days = _safe_int(member.get("window_days"))
        signal_date = _normalize_text(member.get("signal_date"))
        if not signal_date or window_days <= 0:
            continue
        grouped_members[(group_id, window_days, signal_date)].append(member)

    selected_by_entry: Dict[Tuple[str, int, str], Tuple[str, int, str]] = {}
    keys_without_entry: List[Tuple[str, int, str]] = []
    for key in grouped_members.keys():
        group_id, window_days, signal_date = key
        entry_date, _exit_date = rotation_entry_exit_dates(signal_date, normalized_trade_dates)
        if not entry_date:
            keys_without_entry.append(key)
            continue
        selected_key = (group_id, window_days, entry_date)
        existing = selected_by_entry.get(selected_key)
        if existing is None or signal_date > existing[2]:
            selected_by_entry[selected_key] = key

    selected_member_keys = set(selected_by_entry.values())
    selected_member_keys.update(keys_without_entry)

    daily_rows: List[Dict[str, Any]] = []
    for group_id, window_days, signal_date in sorted(selected_member_keys, key=lambda item: (item[0], item[1], item[2])):
        members = sorted(grouped_members[(group_id, window_days, signal_date)], key=lambda item: _safe_int(item.get("rank")))
        entry_date, exit_date = rotation_entry_exit_dates(signal_date, normalized_trade_dates)
        returns: List[float] = []
        holdings: List[Dict[str, Any]] = []
        unresolved_count = 0
        missing_quote_count = 0

        for member in members:
            ts_code = resolve_signal_ts_code(member, stock_basic_index)
            holding = {
                "rank": _safe_int(member.get("rank")),
                "stock_name": _normalize_text(member.get("stock_name")),
                "ts_code": ts_code,
                "mention_count": _safe_int(member.get("mention_count")),
                "return": "",
                "status": "",
            }
            if not ts_code:
                unresolved_count += 1
                holdings.append({**holding, "status": "skipped_unresolved_ts_code"})
                continue
            if not entry_date:
                holdings.append({**holding, "status": "skipped_no_entry_trade_date"})
                continue
            if not exit_date:
                holdings.append({**holding, "status": "skipped_no_exit_trade_date"})
                continue

            entry_quote = quote_lookup.get((ts_code, entry_date))
            exit_quote = quote_lookup.get((ts_code, exit_date))
            if not entry_quote or not _is_tradable_entry_quote(entry_quote):
                missing_quote_count += 1
                holdings.append({**holding, "status": "skipped_missing_or_untradable_entry_quote"})
                continue
            if not exit_quote or not _is_tradable_entry_quote(exit_quote):
                missing_quote_count += 1
                holdings.append({**holding, "status": "skipped_missing_or_untradable_exit_quote"})
                continue

            entry_open = _safe_float(entry_quote.get("open"))
            exit_open = _safe_float(exit_quote.get("open"))
            daily_return = exit_open / entry_open - 1 if entry_open > 0 else 0.0

            returns.append(daily_return)
            holdings.append(
                {
                    **holding,
                    "entry_open": round(entry_open, 6),
                    "exit_open": round(exit_open, 6),
                    "return": round(daily_return, 6),
                    "status": "completed",
                }
            )

        portfolio_return = round(sum(returns) / len(returns), 6) if returns else ""
        if returns:
            status = "completed"
        elif not entry_date:
            status = "skipped_no_entry_trade_date"
        elif not exit_date:
            status = "skipped_no_exit_trade_date"
        else:
            status = "skipped_no_completed_holding"
        daily_rows.append(
            {
                "group_id": group_id,
                "window_days": window_days,
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "pool_size": len(members),
                "resolved_count": len(returns),
                "unresolved_count": unresolved_count,
                "missing_quote_count": missing_quote_count,
                "portfolio_return": portfolio_return,
                "status": status,
                "holdings_json": holdings,
            }
        )

    return daily_rows


def _compound_return(values: Sequence[float]) -> float:
    compounded = 1.0
    for value in values:
        compounded *= 1 + value
    return compounded - 1


def summarize_pool_rotation_period_returns(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, int, str, str], List[Tuple[str, float]]] = defaultdict(list)
    for row in rows:
        if _normalize_text(row.get("status")) != "completed" or _normalize_text(row.get("portfolio_return")) == "":
            continue
        trade_date_text = _normalize_text(row.get("exit_date") or row.get("trade_date"))
        trade_day = _parse_day(trade_date_text, "trade_date")
        iso_year, iso_week, _iso_weekday = trade_day.isocalendar()
        periods = (
            ("week", f"{iso_year}-W{iso_week:02d}"),
            ("month", trade_day.strftime("%Y-%m")),
        )
        for period_type, period in periods:
            groups[
                (
                    _normalize_text(row.get("group_id")),
                    _safe_int(row.get("window_days")),
                    period_type,
                    period,
                )
            ].append((trade_date_text, _safe_float(row.get("portfolio_return"))))

    period_rows: List[Dict[str, Any]] = []
    for key, values in sorted(groups.items(), key=lambda item: item[0]):
        group_id, window_days, period_type, period = key
        trade_dates = [item[0] for item in values]
        returns = [item[1] for item in values]
        period_rows.append(
            {
                "group_id": group_id,
                "window_days": window_days,
                "period_type": period_type,
                "period": period,
                "start_trade_date": min(trade_dates),
                "end_trade_date": max(trade_dates),
                "trading_days": len(returns),
                "compound_return": round(_compound_return(returns), 6),
                "mean_daily_return": round(sum(returns) / len(returns), 6),
                "win_rate": round(sum(1 for value in returns if value > 0) / len(returns), 6),
            }
        )
    return period_rows


def summarize_pool_rotation_backtest(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    row_list = list(rows)
    status_counts: Dict[str, int] = {}
    by_window: Dict[str, Dict[str, Any]] = {}
    returns_by_window: Dict[str, List[float]] = defaultdict(list)
    for row in row_list:
        status = _normalize_text(row.get("status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        window_key = str(_safe_int(row.get("window_days")))
        by_window.setdefault(window_key, {"daily_rows": 0, "completed": 0})
        by_window[window_key]["daily_rows"] += 1
        if status == "completed" and _normalize_text(row.get("portfolio_return")) != "":
            by_window[window_key]["completed"] += 1
            returns_by_window[window_key].append(_safe_float(row.get("portfolio_return")))

    for window_key, returns in returns_by_window.items():
        by_window[window_key]["mean_daily_return"] = round(sum(returns) / len(returns), 6)
        by_window[window_key]["compound_return"] = round(_compound_return(returns), 6)
        by_window[window_key]["win_rate"] = round(sum(1 for value in returns if value > 0) / len(returns), 6)

    return {
        "daily_rows": len(row_list),
        "completed": status_counts.get("completed", 0),
        "skipped": len(row_list) - status_counts.get("completed", 0),
        "status_counts": status_counts,
        "by_window": by_window,
    }
