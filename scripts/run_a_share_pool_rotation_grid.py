from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.a_share_analysis_service import normalize_group_id, read_existing_csv, validate_day
from backend.services.a_share_research_return_smoke_service import (
    _compound_return,
    _is_tradable_entry_quote,
    _normalize_text,
    _parse_day,
    _pool_quote_range_bounds,
    _quotes_by_ts_code_and_day,
    _rotation_entry_exit_dates,
    _safe_float,
    _safe_int,
    build_recommendation_pool_memberships,
    load_knowaction_quotes,
    load_knowaction_stock_basic_index,
    load_knowaction_trade_dates,
    resolve_signal_ts_code,
)


COST_RATES = (0.001, 0.002, 0.005)
SUMMARY_FIELDS = [
    "family",
    "bucket",
    "window_days",
    "daily_rows",
    "completed",
    "mean_daily_return",
    "compound_return",
    "compound_after_10bps",
    "compound_after_20bps",
    "compound_after_50bps",
    "annualized_return",
    "annualized_after_10bps",
    "annualized_after_20bps",
    "annualized_after_50bps",
    "win_rate",
    "avg_turnover",
    "max_drawdown",
    "max_drawdown_after_10bps",
    "max_drawdown_after_20bps",
    "max_drawdown_after_50bps",
]
DAILY_FIELDS = [
    "family",
    "bucket",
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
    "turnover",
    "return_after_10bps",
    "return_after_20bps",
    "return_after_50bps",
    "status",
    "holdings_json",
]
PERIOD_FIELDS = [
    "family",
    "bucket",
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
CONTRIBUTION_FIELDS = [
    "family",
    "bucket",
    "window_days",
    "contribution_rank",
    "ts_code",
    "stock_name",
    "holding_days",
    "positive_days",
    "win_rate",
    "sum_simple_contribution",
    "avg_holding_return",
]


def _parse_windows(value: str) -> tuple[int, ...]:
    windows: list[int] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise argparse.ArgumentTypeError("window range start cannot exceed end")
            windows.extend(range(start, end + 1))
        else:
            windows.append(int(item))
    normalized = tuple(dict.fromkeys(window for window in windows if window > 0))
    if not normalized:
        raise argparse.ArgumentTypeError("windows cannot be empty")
    return normalized


def _parse_bucket(value: str) -> tuple[str, str, int, int]:
    bucket = value.strip().lower()
    if bucket == "all":
        return "topn", "all", 1, 1_000_000

    top_match = re.fullmatch(r"top(\d+)", bucket)
    if top_match:
        top_n = int(top_match.group(1))
        return "topn", f"top{top_n}", 1, top_n

    rank_match = re.fullmatch(r"rank(\d+)_(\d+)", bucket)
    if rank_match:
        start_rank = int(rank_match.group(1))
        end_rank = int(rank_match.group(2))
        if start_rank > end_rank:
            raise argparse.ArgumentTypeError(f"invalid rank bucket: {value}")
        return "rank_bucket", f"rank{start_rank}_{end_rank}", start_rank, end_rank

    raise argparse.ArgumentTypeError(f"unsupported bucket: {value}")


def _parse_buckets(value: str) -> tuple[tuple[str, str, int, int], ...]:
    buckets = tuple(_parse_bucket(item) for item in value.split(",") if item.strip())
    if not buckets:
        raise argparse.ArgumentTypeError("buckets cannot be empty")
    return buckets


def _default_output_prefix(group_id: str, start_date: str | None, end_date: str | None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    start = (start_date or "all").replace("-", "")
    end = (end_date or "all").replace("-", "")
    return Path("output") / "a_share_research" / f"{group_id}_pool_rotation_extended_{start}_{end}_{stamp}"


def _rounded(value: Any, digits: int = 6) -> Any:
    if value == "" or value is None:
        return ""
    return round(float(value), digits)


def _max_drawdown(returns: Sequence[float]) -> float:
    nav = 1.0
    peak = 1.0
    max_dd = 0.0
    for daily_return in returns:
        nav *= 1 + daily_return
        peak = max(peak, nav)
        if peak > 0:
            max_dd = min(max_dd, nav / peak - 1)
    return max_dd


def _annualized(compound: float, days: int) -> float:
    if days <= 0 or compound <= -1:
        return math.nan
    return (1 + compound) ** (252 / days) - 1


def _turnover(previous: set[str], current: set[str]) -> float:
    if not current:
        return 0.0
    if not previous:
        return 1.0
    return 1 - len(previous & current) / len(current)


def _select_members_for_entry(
    grouped_members: Mapping[str, list[Mapping[str, Any]]],
    trade_dates: Sequence[str],
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    selected_by_entry: dict[str, str] = {}
    no_entry_dates: list[str] = []
    for signal_date in grouped_members.keys():
        entry_date, _exit_date = _rotation_entry_exit_dates(signal_date, trade_dates)
        if not entry_date:
            no_entry_dates.append(signal_date)
            continue
        if entry_date not in selected_by_entry or signal_date > selected_by_entry[entry_date]:
            selected_by_entry[entry_date] = signal_date

    selected_dates = sorted(set(selected_by_entry.values()) | set(no_entry_dates))
    return [(signal_date, grouped_members[signal_date]) for signal_date in selected_dates]


def _build_combo_daily_rows(
    *,
    family: str,
    bucket: str,
    group_id: str,
    window_days: int,
    members_by_signal_date: Mapping[str, list[Mapping[str, Any]]],
    quote_lookup: Mapping[tuple[str, str], Mapping[str, Any]],
    trade_dates: Sequence[str],
) -> list[dict[str, Any]]:
    daily_rows: list[dict[str, Any]] = []
    previous_holdings: set[str] = set()

    for signal_date, raw_members in _select_members_for_entry(members_by_signal_date, trade_dates):
        members = sorted(raw_members, key=lambda item: _safe_int(item.get("rank")))
        entry_date, exit_date = _rotation_entry_exit_dates(signal_date, trade_dates)
        holdings: list[dict[str, Any]] = []
        returns: list[float] = []
        current_holdings: set[str] = set()
        unresolved_count = 0
        missing_quote_count = 0

        for bucket_rank, member in enumerate(members, start=1):
            ts_code = _normalize_text(member.get("ts_code")).upper()
            holding = {
                "rank": bucket_rank,
                "source_rank": _safe_int(member.get("rank")),
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
            current_holdings.add(ts_code)
            holdings.append(
                {
                    **holding,
                    "entry_open": round(entry_open, 6),
                    "exit_open": round(exit_open, 6),
                    "return": round(daily_return, 6),
                    "status": "completed",
                }
            )

        portfolio_return = sum(returns) / len(returns) if returns else ""
        turnover = _turnover(previous_holdings, current_holdings) if returns else ""
        if returns:
            status = "completed"
            previous_holdings = current_holdings
        elif not entry_date:
            status = "skipped_no_entry_trade_date"
        elif not exit_date:
            status = "skipped_no_exit_trade_date"
        else:
            status = "skipped_no_completed_holding"

        daily_rows.append(
            {
                "family": family,
                "bucket": bucket,
                "group_id": group_id,
                "window_days": window_days,
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "pool_size": len(members),
                "resolved_count": len(returns),
                "unresolved_count": unresolved_count,
                "missing_quote_count": missing_quote_count,
                "portfolio_return": _rounded(portfolio_return),
                "turnover": _rounded(turnover),
                "return_after_10bps": _rounded(portfolio_return - turnover * COST_RATES[0]) if returns else "",
                "return_after_20bps": _rounded(portfolio_return - turnover * COST_RATES[1]) if returns else "",
                "return_after_50bps": _rounded(portfolio_return - turnover * COST_RATES[2]) if returns else "",
                "status": status,
                "holdings_json": holdings,
            }
        )

    return daily_rows


def _summarize_daily_rows(daily_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        groups[(_normalize_text(row.get("family")), _normalize_text(row.get("bucket")), _safe_int(row.get("window_days")))].append(row)

    summary_rows: list[dict[str, Any]] = []
    for (family, bucket, window_days), rows in sorted(groups.items()):
        completed = [row for row in rows if row.get("status") == "completed" and _normalize_text(row.get("portfolio_return")) != ""]
        returns = [_safe_float(row.get("portfolio_return")) for row in completed]
        turnovers = [_safe_float(row.get("turnover")) for row in completed if _normalize_text(row.get("turnover")) != ""]
        cost_returns = {
            "10bps": [_safe_float(row.get("return_after_10bps")) for row in completed],
            "20bps": [_safe_float(row.get("return_after_20bps")) for row in completed],
            "50bps": [_safe_float(row.get("return_after_50bps")) for row in completed],
        }
        compound = _compound_return(returns) if returns else math.nan
        compound_cost = {key: _compound_return(values) if values else math.nan for key, values in cost_returns.items()}
        summary_rows.append(
            {
                "family": family,
                "bucket": bucket,
                "window_days": window_days,
                "daily_rows": len(rows),
                "completed": len(completed),
                "mean_daily_return": _rounded(sum(returns) / len(returns)) if returns else "",
                "compound_return": _rounded(compound) if returns else "",
                "compound_after_10bps": _rounded(compound_cost["10bps"]) if returns else "",
                "compound_after_20bps": _rounded(compound_cost["20bps"]) if returns else "",
                "compound_after_50bps": _rounded(compound_cost["50bps"]) if returns else "",
                "annualized_return": _rounded(_annualized(compound, len(returns))) if returns else "",
                "annualized_after_10bps": _rounded(_annualized(compound_cost["10bps"], len(returns))) if returns else "",
                "annualized_after_20bps": _rounded(_annualized(compound_cost["20bps"], len(returns))) if returns else "",
                "annualized_after_50bps": _rounded(_annualized(compound_cost["50bps"], len(returns))) if returns else "",
                "win_rate": _rounded(sum(1 for value in returns if value > 0) / len(returns)) if returns else "",
                "avg_turnover": _rounded(sum(turnovers) / len(turnovers)) if turnovers else "",
                "max_drawdown": _rounded(_max_drawdown(returns)) if returns else "",
                "max_drawdown_after_10bps": _rounded(_max_drawdown(cost_returns["10bps"])) if returns else "",
                "max_drawdown_after_20bps": _rounded(_max_drawdown(cost_returns["20bps"])) if returns else "",
                "max_drawdown_after_50bps": _rounded(_max_drawdown(cost_returns["50bps"])) if returns else "",
            }
        )
    return summary_rows


def _summarize_periods(daily_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, int, str, str], list[tuple[str, float]]] = defaultdict(list)
    for row in daily_rows:
        if row.get("status") != "completed" or _normalize_text(row.get("portfolio_return")) == "":
            continue
        trade_date_text = _normalize_text(row.get("exit_date"))
        trade_day = _parse_day(trade_date_text, "trade_date")
        iso_year, iso_week, _ = trade_day.isocalendar()
        periods = (("week", f"{iso_year}-W{iso_week:02d}"), ("month", trade_day.strftime("%Y-%m")))
        for period_type, period in periods:
            groups[
                (
                    _normalize_text(row.get("family")),
                    _normalize_text(row.get("bucket")),
                    _normalize_text(row.get("group_id")),
                    _safe_int(row.get("window_days")),
                    period_type,
                    period,
                )
            ].append((trade_date_text, _safe_float(row.get("portfolio_return"))))

    period_rows: list[dict[str, Any]] = []
    for (family, bucket, group_id, window_days, period_type, period), values in sorted(groups.items()):
        trade_dates = [item[0] for item in values]
        returns = [item[1] for item in values]
        period_rows.append(
            {
                "family": family,
                "bucket": bucket,
                "group_id": group_id,
                "window_days": window_days,
                "period_type": period_type,
                "period": period,
                "start_trade_date": min(trade_dates),
                "end_trade_date": max(trade_dates),
                "trading_days": len(returns),
                "compound_return": _rounded(_compound_return(returns)),
                "mean_daily_return": _rounded(sum(returns) / len(returns)),
                "win_rate": _rounded(sum(1 for value in returns if value > 0) / len(returns)),
            }
        )
    return period_rows


def _summarize_contributions(daily_rows: Iterable[Mapping[str, Any]], *, top_n: int = 10) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int, str, str], dict[str, Any]] = {}
    for row in daily_rows:
        if row.get("status") != "completed":
            continue
        holdings = row.get("holdings_json") or []
        resolved_count = _safe_int(row.get("resolved_count"))
        if not resolved_count:
            continue
        for holding in holdings:
            if _normalize_text(holding.get("status")) != "completed":
                continue
            key = (
                _normalize_text(row.get("family")),
                _normalize_text(row.get("bucket")),
                _safe_int(row.get("window_days")),
                _normalize_text(holding.get("ts_code")).upper(),
                _normalize_text(holding.get("stock_name")),
            )
            stats = groups.setdefault(key, {"holding_days": 0, "positive_days": 0, "sum_return": 0.0, "sum_simple_contribution": 0.0})
            holding_return = _safe_float(holding.get("return"))
            stats["holding_days"] += 1
            stats["positive_days"] += 1 if holding_return > 0 else 0
            stats["sum_return"] += holding_return
            stats["sum_simple_contribution"] += holding_return / resolved_count

    by_combo: dict[tuple[str, str, int], list[tuple[tuple[str, str, int, str, str], dict[str, Any]]]] = defaultdict(list)
    for key, stats in groups.items():
        by_combo[key[:3]].append((key, stats))

    rows: list[dict[str, Any]] = []
    for combo, values in sorted(by_combo.items()):
        ranked = sorted(values, key=lambda item: item[1]["sum_simple_contribution"], reverse=True)[:top_n]
        for rank, (key, stats) in enumerate(ranked, start=1):
            family, bucket, window_days, ts_code, stock_name = key
            holding_days = stats["holding_days"]
            rows.append(
                {
                    "family": family,
                    "bucket": bucket,
                    "window_days": window_days,
                    "contribution_rank": rank,
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "holding_days": holding_days,
                    "positive_days": stats["positive_days"],
                    "win_rate": _rounded(stats["positive_days"] / holding_days) if holding_days else "",
                    "sum_simple_contribution": _rounded(stats["sum_simple_contribution"]),
                    "avg_holding_return": _rounded(stats["sum_return"] / holding_days) if holding_days else "",
                }
            )
    return rows


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: json.dumps(row.get(field, ""), ensure_ascii=False) if isinstance(row.get(field), (dict, list, tuple)) else row.get(field, "")
                    for field in fields
                }
            )
    return path


def run_grid(
    *,
    group_id: str,
    start_date: str | None,
    end_date: str | None,
    windows: Sequence[int],
    buckets: Sequence[tuple[str, str, int, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_group_id = normalize_group_id(group_id)
    if not normalized_group_id:
        raise ValueError("group_id cannot be empty")

    start_day = validate_day(start_date, "start_date") or None
    end_day = validate_day(end_date, "end_date") or None
    max_rank = max(end_rank for _family, _bucket, _start_rank, end_rank in buckets)

    daily_mentions = read_existing_csv(group_id=normalized_group_id)
    membership_rows = build_recommendation_pool_memberships(
        daily_mentions,
        group_id=normalized_group_id,
        start_date=start_day,
        end_date=end_day,
        windows=windows,
        ranking_top_n=max_rank,
    )
    if not membership_rows:
        return [], [], [], []

    stock_basic_index = load_knowaction_stock_basic_index()
    membership_with_codes = [{**row, "ts_code": resolve_signal_ts_code(row, stock_basic_index)} for row in membership_rows]
    quote_start, quote_end = _pool_quote_range_bounds(membership_with_codes)
    quote_end = quote_end + timedelta(days=5)
    trade_dates = load_knowaction_trade_dates(quote_start, quote_end)
    quotes = load_knowaction_quotes([row["ts_code"] for row in membership_with_codes], quote_start, quote_end)
    quote_lookup = _quotes_by_ts_code_and_day(quotes)

    by_window_signal: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in membership_with_codes:
        by_window_signal[(_safe_int(row.get("window_days")), _normalize_text(row.get("signal_date")))].append(row)

    daily_rows: list[dict[str, Any]] = []
    for window_days in windows:
        signals = sorted(signal_date for (window, signal_date) in by_window_signal.keys() if window == window_days)
        for family, bucket, start_rank, end_rank in buckets:
            members_by_signal_date: dict[str, list[Mapping[str, Any]]] = {}
            for signal_date in signals:
                members = [
                    row
                    for row in by_window_signal[(window_days, signal_date)]
                    if start_rank <= _safe_int(row.get("rank")) <= end_rank
                ]
                if members:
                    members_by_signal_date[signal_date] = members
            daily_rows.extend(
                _build_combo_daily_rows(
                    family=family,
                    bucket=bucket,
                    group_id=normalized_group_id,
                    window_days=window_days,
                    members_by_signal_date=members_by_signal_date,
                    quote_lookup=quote_lookup,
                    trade_dates=trade_dates,
                )
            )

    summary_rows = _summarize_daily_rows(daily_rows)
    period_rows = _summarize_periods(daily_rows)
    contribution_rows = _summarize_contributions(daily_rows)
    return summary_rows, daily_rows, period_rows, contribution_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a focused A-share recommendation-pool rotation grid.")
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--windows", type=_parse_windows, default=_parse_windows("1-60"))
    parser.add_argument("--buckets", type=_parse_buckets, default=_parse_buckets("rank21_40,rank21_30,rank56_60,top50"))
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--skip-daily", action="store_true", help="Do not write the potentially large daily holdings CSV.")
    args = parser.parse_args()

    prefix = Path(args.output_prefix) if args.output_prefix else _default_output_prefix(args.group_id, args.start_date, args.end_date)
    summary_rows, daily_rows, period_rows, contribution_rows = run_grid(
        group_id=args.group_id,
        start_date=args.start_date,
        end_date=args.end_date,
        windows=args.windows,
        buckets=args.buckets,
    )
    outputs = {
        "summary": str(_write_csv(prefix.with_name(prefix.name + "_summary.csv"), SUMMARY_FIELDS, summary_rows)),
        "period": str(_write_csv(prefix.with_name(prefix.name + "_period.csv"), PERIOD_FIELDS, period_rows)),
        "contribution": str(_write_csv(prefix.with_name(prefix.name + "_contribution.csv"), CONTRIBUTION_FIELDS, contribution_rows)),
    }
    if not args.skip_daily:
        outputs["daily"] = str(_write_csv(prefix.with_name(prefix.name + "_daily.csv"), DAILY_FIELDS, daily_rows))

    print(
        json.dumps(
            {
                "outputs": outputs,
                "summary_rows": len(summary_rows),
                "daily_rows": len(daily_rows),
                "period_rows": len(period_rows),
                "contribution_rows": len(contribution_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
