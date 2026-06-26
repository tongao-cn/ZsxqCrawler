from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from backend.services.retention_cleanup_service import (
    DEFAULT_RETENTION_DAYS,
    preview_group_retention_cleanup,
    run_group_retention_cleanup,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or apply group retention cleanup.")
    parser.add_argument("--group-id", required=True, help="Knowledge Planet group id.")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS, help="Days of content to keep.")
    parser.add_argument("--apply", action="store_true", help="Apply deletion. Omit to run a dry-run preview.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    return parser


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _json_text(payload: dict[str, Any], *, compact: bool) -> str:
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.apply:
        return run_group_retention_cleanup(
            args.group_id,
            retention_days=args.retention_days,
            log_callback=_log,
        )
    return preview_group_retention_cleanup(args.group_id, retention_days=args.retention_days)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = _run(args)
    sys.stdout.buffer.write((_json_text(payload, compact=args.compact) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
