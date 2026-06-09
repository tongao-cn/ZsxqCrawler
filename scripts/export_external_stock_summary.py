from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.services.stock_external_summary_service import get_external_stock_summaries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export read-only saved stock summaries as JSON without starting the API server")
    parser.add_argument("--group-id", required=True, help="Knowledge Planet group id.")
    parser.add_argument(
        "--stock-names",
        nargs="+",
        required=True,
        help="Stock names or codes. Supports spaces, commas, Chinese commas, or repeated values.",
    )
    parser.add_argument("--date", default=None, help="Optional daily concept date, YYYY-MM-DD. Omit to use latest available concept rows.")
    parser.add_argument("--output", default=None, help="Optional output JSON path. Omit to print UTF-8 JSON to stdout.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON instead of pretty JSON.")
    return parser


def _json_text(payload: dict[str, Any], *, compact: bool) -> str:
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _write_payload(payload: dict[str, Any], *, output: str | None, compact: bool) -> None:
    text = _json_text(payload, compact=compact)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {output_path}")
        return
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = get_external_stock_summaries(
        args.group_id,
        args.stock_names,
        report_date=args.date,
    )
    _write_payload(payload, output=args.output, compact=args.compact)


if __name__ == "__main__":
    main()
