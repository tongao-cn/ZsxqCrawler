"""A-share research return smoke backed by KnowActionSystem quotes."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.services.a_share_analysis_service import (
    DEFAULT_RANKING_TOP_N,
    DEFAULT_RANKING_WINDOWS,
    normalize_group_id,
    read_existing_csv,
)
from backend.services.a_share_pool_rotation_backtest import (
    DEFAULT_POOL_ROTATION_DAILY_FIELDS,
    DEFAULT_POOL_ROTATION_PERIOD_FIELDS,
    build_pool_rotation_daily_rows,
    build_recommendation_pool_memberships as _build_recommendation_pool_memberships,
    pool_quote_range_bounds as _pool_quote_range_bounds,
    summarize_pool_rotation_backtest,
    summarize_pool_rotation_period_returns,
)
from backend.services.a_share_knowaction_market_data import (
    DEFAULT_KNOW_ACTION_ENV_PATH,
    DEFAULT_TRADE_CALENDAR_EXCHANGE,
    get_knowaction_connection,
    get_knowaction_postgres_dsn,
    load_knowaction_quotes,
    load_knowaction_stock_basic_index,
    load_knowaction_trade_dates,
)
from backend.services.a_share_research_export_service import load_a_share_research_dataset
from backend.services.a_share_return_smoke_backtest import (
    DEFAULT_RETURN_HOLD_DAYS,
    DEFAULT_RETURN_SMOKE_FIELDS,
    build_return_smoke_rows,
    return_smoke_quote_range_bounds as _quote_range_bounds,
    summarize_return_smoke,
)
from backend.services.a_share_signal_codes import (
    resolve_signal_ts_code,
)


DEFAULT_POOL_ROTATION_WINDOWS = DEFAULT_RANKING_WINDOWS
DEFAULT_POOL_ROTATION_TOP_N = DEFAULT_RANKING_TOP_N


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


def build_recommendation_pool_memberships(
    daily_mentions: Mapping[str, Mapping[str, int]],
    *,
    group_id: Any = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    windows: Sequence[int] = DEFAULT_POOL_ROTATION_WINDOWS,
    ranking_top_n: int = DEFAULT_POOL_ROTATION_TOP_N,
) -> List[Dict[str, Any]]:
    return _build_recommendation_pool_memberships(
        daily_mentions,
        group_id=group_id,
        start_date=start_date,
        end_date=end_date,
        windows=windows,
        ranking_top_n=ranking_top_n,
    )


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
    trade_dates = load_knowaction_trade_dates(quote_start, quote_end, env_path=env_path)
    quotes = load_knowaction_quotes(
        [row["ts_code"] for row in membership_with_codes],
        quote_start,
        quote_end,
        env_path,
    )
    daily_rows = build_pool_rotation_daily_rows(
        membership_with_codes,
        quotes,
        trade_dates=trade_dates,
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
    "DEFAULT_TRADE_CALENDAR_EXCHANGE",
    "build_pool_rotation_daily_rows",
    "build_recommendation_pool_memberships",
    "build_return_smoke_rows",
    "get_knowaction_postgres_dsn",
    "load_knowaction_trade_dates",
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
