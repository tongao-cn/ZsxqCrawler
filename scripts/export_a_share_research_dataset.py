from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from backend.services.a_share_research_export_service import (
    load_a_share_research_dataset,
    write_a_share_research_dataset_csv,
)


def _default_output_path(group_id: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("output") / "a_share_research" / f"{group_id}_research_dataset_{stamp}.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export group-scoped A-share research dataset CSV")
    parser.add_argument("--group-id", required=True, help="Knowledge Planet group id.")
    parser.add_argument("--start-date", default=None, help="Optional signal start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Optional signal end date, YYYY-MM-DD.")
    parser.add_argument("--output", default=None, help="Output CSV path.")
    args = parser.parse_args()

    rows = load_a_share_research_dataset(
        group_id=args.group_id,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    output_path = Path(args.output) if args.output else _default_output_path(str(args.group_id).strip())
    written_path = write_a_share_research_dataset_csv(rows, output_path)
    print(f"Wrote {len(rows)} rows: {written_path}")


if __name__ == "__main__":
    main()
