#!/usr/bin/env python3
import argparse
import sys

from backend.services.a_share_analysis_service import (
    DEFAULT_API_BASE,
    DEFAULT_CONCURRENCY,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_WIRE_API,
    ensure_configured,
    run_analysis,
)


def main():
    ensure_configured()

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--api_base", type=str, default=DEFAULT_API_BASE)
    parser.add_argument("--wire_api", type=str, default=DEFAULT_WIRE_API)
    parser.add_argument("--reasoning_effort", type=str, default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--reset_start_date", type=str, default=None)
    parser.add_argument("--reset_end_date", type=str, default=None)
    args = parser.parse_args()

    try:
        result = run_analysis(
            days=args.days,
            model=args.model,
            api_base=args.api_base,
            wire_api=args.wire_api,
            reasoning_effort=args.reasoning_effort,
            concurrency=args.concurrency,
            reset_start_date=args.reset_start_date,
            reset_end_date=args.reset_end_date,
        )
    except Exception as exc:
        print(str(exc))
        sys.exit(1)

    print(f"Saved: {result['output_path']}")


if __name__ == "__main__":
    main()
