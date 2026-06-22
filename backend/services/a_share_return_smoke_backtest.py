"""A-share return smoke backtest calculations."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from backend.services.a_share_signal_codes import resolve_signal_ts_code


DEFAULT_RETURN_HOLD_DAYS = 5
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


def return_smoke_quote_range_bounds(signal_rows: Sequence[Mapping[str, Any]], hold_days: int) -> Tuple[date, date]:
    signal_dates = [_parse_day(row.get("signal_date"), "signal_date") for row in signal_rows if row.get("signal_date")]
    if not signal_dates:
        raise ValueError("没有可用于收益 smoke 的 signal_date")
    start_date = min(signal_dates)
    end_date = max(signal_dates) + timedelta(days=max(hold_days, 1) * 3 + 10)
    return start_date, end_date


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
            results.append(
                {
                    **base,
                    "entry_date": entry_quote["trade_date"],
                    "entry_open": entry_quote["open"],
                    "status": "skipped_no_tradable_exit",
                }
            )
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
