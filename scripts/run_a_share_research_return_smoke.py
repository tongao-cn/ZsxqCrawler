from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from backend.services.a_share_research_return_smoke_service import (
    DEFAULT_RETURN_HOLD_DAYS,
    run_a_share_return_smoke,
    write_return_smoke_csv,
)


def _default_output_path(group_id: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("output") / "a_share_research" / f"{group_id}_return_smoke_{stamp}.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a KnowAction-backed return smoke for A-share research signals")
    parser.add_argument("--group-id", required=True, help="Knowledge Planet group id.")
    parser.add_argument("--start-date", default=None, help="Optional signal start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Optional signal end date, YYYY-MM-DD.")
    parser.add_argument("--hold-days", type=int, default=DEFAULT_RETURN_HOLD_DAYS, help="Tradable close count after T+1 open entry.")
    parser.add_argument("--output", default=None, help="Output trade-level CSV path.")
    args = parser.parse_args()

    rows, summary = run_a_share_return_smoke(
        group_id=args.group_id,
        start_date=args.start_date,
        end_date=args.end_date,
        hold_days=args.hold_days,
    )
    output_path = Path(args.output) if args.output else _default_output_path(str(args.group_id).strip())
    written_path = write_return_smoke_csv(rows, output_path)
    print(json.dumps({"output": str(written_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
