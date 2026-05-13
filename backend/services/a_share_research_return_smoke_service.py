"""A-share research return smoke backed by KnowActionSystem quotes."""

from __future__ import annotations

import csv
import json
import os
from bisect import bisect_right
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import psycopg2

from backend.services.a_share_analysis_service import (
    DEFAULT_RANKING_TOP_N,
    DEFAULT_RANKING_WINDOWS,
    normalize_group_id,
    read_existing_csv,
    validate_day,
)
from backend.services.a_share_research_export_service import load_a_share_research_dataset


DEFAULT_KNOW_ACTION_ENV_PATH = Path(os.getenv("KNOW_ACTION_ENV_PATH", r"C:\Dev\KnowActionSystem\.env"))
DEFAULT_RETURN_HOLD_DAYS = 5
DEFAULT_POOL_ROTATION_WINDOWS = DEFAULT_RANKING_WINDOWS
DEFAULT_POOL_ROTATION_TOP_N = DEFAULT_RANKING_TOP_N
DEFAULT_RETURN_SMOKE_FIELDS = [
    "group_id",
    "signal_date",
    "stock_name",
    "stock_code",
    "market",
    "ts_code",
    "mention_count",
    "topic_count",
    "concepts",
    "avg_confidence",
    "max_confidence",
    "hold_days",
    "entry_date",
    "exit_date",
    "entry_open",
    "exit_close",
    "gross_return",
    "status",
]
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


def _load_env_file(path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _resolve_setting(key: str, env_values: Mapping[str, str]) -> str:
    return _normalize_text(os.getenv(key) or env_values.get(key))


def get_knowaction_postgres_dsn(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> str:
    direct_dsn = _normalize_text(os.getenv("KNOW_ACTION_POSTGRES_DSN") or os.getenv("KNOWACTION_POSTGRES_DSN"))
    if direct_dsn:
        return direct_dsn

    env_values = _load_env_file(env_path)
    host = _resolve_setting("DB_HOST", env_values)
    port = _resolve_setting("DB_PORT", env_values) or "5432"
    name = _resolve_setting("DB_NAME", env_values)
    user = _resolve_setting("DB_USER", env_values)
    password = _resolve_setting("DB_PASSWORD", env_values)
    if not all([host, port, name, user]):
        raise RuntimeError("未找到 KnowActionSystem PostgreSQL 配置，请检查 KNOW_ACTION_ENV_PATH 或 C:\\Dev\\KnowActionSystem\\.env")
    return f"dbname={name} user={user} password={password} host={host} port={port}"


@contextmanager
def get_knowaction_connection(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Iterator[Any]:
    conn = psycopg2.connect(get_knowaction_postgres_dsn(env_path))
    try:
        yield conn
    finally:
        conn.close()


def _company_key(value: Any) -> str:
    key = (
        _normalize_text(value)
        .replace(" ", "")
        .replace("　", "")
        .replace("*", "")
        .replace("－", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("股份有限公司", "")
        .replace("有限责任公司", "")
        .replace("有限公司", "")
        .replace("集团", "")
    )
    for suffix in ("-UW", "-U", "-W", "-B"):
        if key.upper().endswith(suffix):
            key = key[: -len(suffix)]
            break
    for prefix in ("DR", "XD", "XR", "ST"):
        if key.upper().startswith(prefix) and len(key) > len(prefix):
            key = key[len(prefix) :]
            break
    return key


def load_knowaction_stock_basic_index(env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH) -> Dict[str, str]:
    with get_knowaction_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts_code, symbol, name
                FROM stock_basic
                ORDER BY ts_code ASC
                """
            )
            rows = cur.fetchall()

    lookup: Dict[str, str] = {}
    duplicates = set()
    for ts_code, symbol, name in rows:
        normalized_ts_code = _normalize_text(ts_code).upper()
        if not normalized_ts_code:
            continue
        keys = {_company_key(name), _normalize_text(symbol)}
        for key in keys:
            if not key:
                continue
            if key in lookup and lookup[key] != normalized_ts_code:
                duplicates.add(key)
                continue
            lookup[key] = normalized_ts_code
    for key in duplicates:
        lookup.pop(key, None)
    return lookup


def _infer_market_from_symbol(symbol: str) -> str:
    if symbol.startswith("6"):
        return "SH"
    if symbol.startswith(("0", "3")):
        return "SZ"
    if symbol.startswith(("4", "8", "9")):
        return "BJ"
    return ""


def resolve_signal_ts_code(signal: Mapping[str, Any], stock_basic_index: Mapping[str, str] | None = None) -> str:
    raw_ts_code = _normalize_text(signal.get("ts_code")).upper()
    if "." in raw_ts_code:
        return raw_ts_code

    stock_code = _normalize_text(signal.get("stock_code") or signal.get("symbol")).upper()
    if "." in stock_code:
        return stock_code
    market = _normalize_text(signal.get("market")).upper()
    if stock_code and not market:
        market = _infer_market_from_symbol(stock_code)
    if stock_code and market:
        return f"{stock_code}.{market}"

    lookup = stock_basic_index or {}
    return lookup.get(_company_key(signal.get("stock_name")), "")


def _quote_range_bounds(signal_rows: Sequence[Mapping[str, Any]], hold_days: int) -> Tuple[date, date]:
    signal_dates = [_parse_day(row.get("signal_date"), "signal_date") for row in signal_rows if row.get("signal_date")]
    if not signal_dates:
        raise ValueError("没有可用于收益 smoke 的 signal_date")
    start_date = min(signal_dates)
    end_date = max(signal_dates) + timedelta(days=max(hold_days, 1) * 3 + 10)
    return start_date, end_date


def load_knowaction_quotes(
    ts_codes: Sequence[str],
    start_date: date,
    end_date: date,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> List[Dict[str, Any]]:
    normalized_ts_codes = sorted({_normalize_text(code).upper() for code in ts_codes if _normalize_text(code)})
    if not normalized_ts_codes:
        return []

    with get_knowaction_connection(env_path) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts_code, trade_date, open, close, vol, amount
                FROM daily_quotes
                WHERE ts_code = ANY(%s)
                  AND trade_date >= %s
                  AND trade_date <= %s
                ORDER BY ts_code ASC, trade_date ASC
                """,
                (normalized_ts_codes, start_date, end_date),
            )
            return [
                {
                    "ts_code": _normalize_text(row[0]).upper(),
                    "trade_date": row[1].isoformat() if hasattr(row[1], "isoformat") else _normalize_text(row[1]),
                    "open": _safe_float(row[2]),
                    "close": _safe_float(row[3]),
                    "vol": _safe_float(row[4]),
                    "amount": _safe_float(row[5]),
                }
                for row in cur.fetchall()
            ]


def _is_tradable_quote(quote: Mapping[str, Any]) -> bool:
    return _safe_float(quote.get("close")) > 0 and (_safe_float(quote.get("amount")) > 0 or _safe_float(quote.get("vol")) > 0)


def _is_tradable_entry_quote(quote: Mapping[str, Any]) -> bool:
    return _is_tradable_quote(quote) and _safe_float(quote.get("open")) > 0


def _quotes_by_ts_code(quote_rows: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for raw in quote_rows:
        ts_code = _normalize_text(raw.get("ts_code")).upper()
        trade_date = _normalize_text(raw.get("trade_date"))
        if not ts_code or not trade_date:
            continue
        grouped.setdefault(ts_code, []).append(
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "open": _safe_float(raw.get("open")),
                "close": _safe_float(raw.get("close")),
                "vol": _safe_float(raw.get("vol")),
                "amount": _safe_float(raw.get("amount")),
            }
        )
    for rows in grouped.values():
        rows.sort(key=lambda item: item["trade_date"])
    return grouped


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
    windows: Sequence[int] = DEFAULT_POOL_ROTATION_WINDOWS,
    ranking_top_n: int = DEFAULT_POOL_ROTATION_TOP_N,
) -> List[Dict[str, Any]]:
    start_day = validate_day(start_date, "start_date") or ""
    end_day = validate_day(end_date, "end_date") or ""
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


def _pool_quote_range_bounds(membership_rows: Sequence[Mapping[str, Any]]) -> Tuple[date, date]:
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


def _trade_dates_from_quotes(quote_rows: Iterable[Mapping[str, Any]]) -> List[str]:
    trade_dates = sorted({_normalize_text(row.get("trade_date")) for row in quote_rows if _normalize_text(row.get("trade_date"))})
    for trade_date in trade_dates:
        _parse_day(trade_date, "trade_date")
    return trade_dates


def _rotation_entry_exit_dates(signal_date: str, trade_dates: Sequence[str]) -> Tuple[str, str]:
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
    stock_basic_index: Mapping[str, str] | None = None,
) -> List[Dict[str, Any]]:
    quote_list = list(quote_rows)
    quote_lookup = _quotes_by_ts_code_and_day(quote_list)
    trade_dates = _trade_dates_from_quotes(quote_list)
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
        entry_date, _exit_date = _rotation_entry_exit_dates(signal_date, trade_dates)
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
        entry_date, exit_date = _rotation_entry_exit_dates(signal_date, trade_dates)
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


def build_return_smoke_rows(
    signal_rows: Iterable[Mapping[str, Any]],
    quote_rows: Iterable[Mapping[str, Any]],
    *,
    stock_basic_index: Mapping[str, str] | None = None,
    hold_days: int = DEFAULT_RETURN_HOLD_DAYS,
) -> List[Dict[str, Any]]:
    normalized_hold_days = max(1, int(hold_days))
    grouped_quotes = _quotes_by_ts_code(quote_rows)
    results: List[Dict[str, Any]] = []

    for signal in signal_rows:
        ts_code = resolve_signal_ts_code(signal, stock_basic_index)
        signal_date_text = _normalize_text(signal.get("signal_date"))
        base = {
            "group_id": _normalize_text(signal.get("group_id")),
            "signal_date": signal_date_text,
            "stock_name": _normalize_text(signal.get("stock_name")),
            "stock_code": _normalize_text(signal.get("stock_code")),
            "market": _normalize_text(signal.get("market")).upper(),
            "ts_code": ts_code,
            "mention_count": _safe_int(signal.get("mention_count")),
            "topic_count": _safe_int(signal.get("topic_count")),
            "concepts": signal.get("concepts") or [],
            "avg_confidence": _safe_float(signal.get("avg_confidence")),
            "max_confidence": _safe_float(signal.get("max_confidence")),
            "hold_days": normalized_hold_days,
            "entry_date": "",
            "exit_date": "",
            "entry_open": "",
            "exit_close": "",
            "gross_return": "",
            "status": "",
        }
        if not ts_code:
            results.append({**base, "status": "skipped_unresolved_ts_code"})
            continue
        try:
            signal_date = _parse_day(signal_date_text, "signal_date")
        except ValueError:
            results.append({**base, "status": "skipped_invalid_signal_date"})
            continue

        stock_quotes = grouped_quotes.get(ts_code, [])
        future_quotes = [
            quote
            for quote in stock_quotes
            if _parse_day(quote["trade_date"], "trade_date") > signal_date and _is_tradable_entry_quote(quote)
        ]
        if not future_quotes:
            results.append({**base, "status": "skipped_no_tradable_entry"})
            continue

        entry_quote = future_quotes[0]
        entry_date = _parse_day(entry_quote["trade_date"], "trade_date")
        exit_candidates = [
            quote
            for quote in stock_quotes
            if _parse_day(quote["trade_date"], "trade_date") >= entry_date and _is_tradable_quote(quote)
        ]
        if not exit_candidates:
            results.append({**base, "entry_date": entry_quote["trade_date"], "entry_open": entry_quote["open"], "status": "skipped_no_tradable_exit"})
            continue

        forced_exit = len(exit_candidates) < normalized_hold_days
        exit_quote = exit_candidates[min(normalized_hold_days, len(exit_candidates)) - 1]
        entry_open = _safe_float(entry_quote["open"])
        exit_close = _safe_float(exit_quote["close"])
        gross_return = exit_close / entry_open - 1 if entry_open > 0 else 0.0
        results.append(
            {
                **base,
                "entry_date": entry_quote["trade_date"],
                "exit_date": exit_quote["trade_date"],
                "entry_open": round(entry_open, 6),
                "exit_close": round(exit_close, 6),
                "gross_return": round(gross_return, 6),
                "status": "completed_forced_end_of_sample" if forced_exit else "completed",
            }
        )

    return results


def summarize_return_smoke(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    row_list = list(rows)
    completed_returns = [
        _safe_float(row.get("gross_return"))
        for row in row_list
        if _normalize_text(row.get("status")).startswith("completed") and _normalize_text(row.get("gross_return")) != ""
    ]
    status_counts: Dict[str, int] = {}
    for row in row_list:
        status = _normalize_text(row.get("status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "rows": len(row_list),
        "completed": len(completed_returns),
        "skipped": len(row_list) - len(completed_returns),
        "status_counts": status_counts,
        "mean_return": round(sum(completed_returns) / len(completed_returns), 6) if completed_returns else None,
        "median_return": round(median(completed_returns), 6) if completed_returns else None,
        "win_rate": round(sum(1 for value in completed_returns if value > 0) / len(completed_returns), 6) if completed_returns else None,
    }


def run_a_share_return_smoke(
    *,
    group_id: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hold_days: int = DEFAULT_RETURN_HOLD_DAYS,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    signal_rows = load_a_share_research_dataset(group_id=group_id, start_date=start_date, end_date=end_date)
    if not signal_rows:
        return [], summarize_return_smoke([])

    stock_basic_index = load_knowaction_stock_basic_index(env_path)
    signal_with_codes = [
        {**row, "ts_code": resolve_signal_ts_code(row, stock_basic_index)}
        for row in signal_rows
    ]
    quote_start, quote_end = _quote_range_bounds(signal_with_codes, hold_days)
    quotes = load_knowaction_quotes(
        [row["ts_code"] for row in signal_with_codes],
        quote_start,
        quote_end,
        env_path,
    )
    rows = build_return_smoke_rows(
        signal_with_codes,
        quotes,
        stock_basic_index=stock_basic_index,
        hold_days=hold_days,
    )
    return rows, summarize_return_smoke(rows)


def run_recommendation_pool_rotation_backtest(
    *,
    group_id: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    windows: Sequence[int] = DEFAULT_POOL_ROTATION_WINDOWS,
    ranking_top_n: int = DEFAULT_POOL_ROTATION_TOP_N,
    env_path: Path = DEFAULT_KNOW_ACTION_ENV_PATH,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        raise ValueError("group_id 不能为空")

    daily_mentions = read_existing_csv(group_id=normalized_group_id)
    membership_rows = build_recommendation_pool_memberships(
        daily_mentions,
        group_id=normalized_group_id,
        start_date=start_date,
        end_date=end_date,
        windows=windows,
        ranking_top_n=ranking_top_n,
    )
    if not membership_rows:
        empty_summary = summarize_pool_rotation_backtest([])
        return [], [], empty_summary

    stock_basic_index = load_knowaction_stock_basic_index(env_path)
    membership_with_codes = [
        {**row, "ts_code": resolve_signal_ts_code(row, stock_basic_index)}
        for row in membership_rows
    ]
    quote_start, quote_end = _pool_quote_range_bounds(membership_with_codes)
    quotes = load_knowaction_quotes(
        [row["ts_code"] for row in membership_with_codes],
        quote_start,
        quote_end,
        env_path,
    )
    daily_rows = build_pool_rotation_daily_rows(
        membership_with_codes,
        quotes,
        stock_basic_index=stock_basic_index,
    )
    period_rows = summarize_pool_rotation_period_returns(daily_rows)
    return daily_rows, period_rows, summarize_pool_rotation_backtest(daily_rows)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_return_smoke_csv(rows: Iterable[Mapping[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_RETURN_SMOKE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_RETURN_SMOKE_FIELDS})
    return path


def write_pool_rotation_daily_csv(rows: Iterable[Mapping[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_POOL_ROTATION_DAILY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_POOL_ROTATION_DAILY_FIELDS})
    return path


def write_pool_rotation_period_csv(rows: Iterable[Mapping[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DEFAULT_POOL_ROTATION_PERIOD_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in DEFAULT_POOL_ROTATION_PERIOD_FIELDS})
    return path


__all__ = [
    "DEFAULT_POOL_ROTATION_DAILY_FIELDS",
    "DEFAULT_POOL_ROTATION_PERIOD_FIELDS",
    "DEFAULT_POOL_ROTATION_TOP_N",
    "DEFAULT_POOL_ROTATION_WINDOWS",
    "DEFAULT_RETURN_HOLD_DAYS",
    "DEFAULT_RETURN_SMOKE_FIELDS",
    "build_pool_rotation_daily_rows",
    "build_recommendation_pool_memberships",
    "build_return_smoke_rows",
    "get_knowaction_postgres_dsn",
    "resolve_signal_ts_code",
    "run_recommendation_pool_rotation_backtest",
    "run_a_share_return_smoke",
    "summarize_pool_rotation_backtest",
    "summarize_pool_rotation_period_returns",
    "summarize_return_smoke",
    "write_pool_rotation_daily_csv",
    "write_pool_rotation_period_csv",
    "write_return_smoke_csv",
]
