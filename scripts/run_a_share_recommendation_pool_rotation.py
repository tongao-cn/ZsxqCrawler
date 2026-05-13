from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from backend.services.a_share_research_return_smoke_service import (
    DEFAULT_POOL_ROTATION_TOP_N,
    DEFAULT_POOL_ROTATION_WINDOWS,
    run_recommendation_pool_rotation_backtest,
    write_pool_rotation_daily_csv,
    write_pool_rotation_period_csv,
)


def _parse_windows(value: str) -> tuple[int, ...]:
    windows = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not windows:
        raise argparse.ArgumentTypeError("windows 不能为空")
    if any(window <= 0 for window in windows):
        raise argparse.ArgumentTypeError("windows 必须为正整数")
    return windows


def _default_output_paths(group_id: str) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path("output") / "a_share_research"
    return (
        base / f"{group_id}_pool_rotation_daily_{stamp}.csv",
        base / f"{group_id}_pool_rotation_period_{stamp}.csv",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a KnowAction-backed rotating portfolio backtest for A-share recommendation pools")
    parser.add_argument("--group-id", required=True, help="Knowledge Planet group id.")
    parser.add_argument("--start-date", default=None, help="Optional signal start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Optional signal end date, YYYY-MM-DD.")
    parser.add_argument(
        "--windows",
        type=_parse_windows,
        default=DEFAULT_POOL_ROTATION_WINDOWS,
        help="Comma-separated recommendation-pool windows, default: 3,7,14,21.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_POOL_ROTATION_TOP_N,
        help="Recommendation pool size per window. Use 0 or a negative value to include all ranked stocks.",
    )
    parser.add_argument("--daily-output", default=None, help="Output daily portfolio CSV path.")
    parser.add_argument("--period-output", default=None, help="Output weekly/monthly summary CSV path.")
    args = parser.parse_args()

    daily_rows, period_rows, summary = run_recommendation_pool_rotation_backtest(
        group_id=args.group_id,
        start_date=args.start_date,
        end_date=args.end_date,
        windows=args.windows,
        ranking_top_n=args.top_n,
    )
    default_daily_path, default_period_path = _default_output_paths(str(args.group_id).strip())
    daily_output = Path(args.daily_output) if args.daily_output else default_daily_path
    period_output = Path(args.period_output) if args.period_output else default_period_path
    daily_path = write_pool_rotation_daily_csv(daily_rows, daily_output)
    period_path = write_pool_rotation_period_csv(period_rows, period_output)
    print(
        json.dumps(
            {
                "daily_output": str(daily_path),
                "period_output": str(period_path),
                "period_rows": len(period_rows),
                **summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
