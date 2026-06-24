from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.core.console_output import safe_console_print
from backend.services import stock_topic_analysis_service as stock_topic_service
from backend.storage.db_compat import connect


DEFAULT_GROUP_ID = "51111112855254"
DEFAULT_PENDING_THRESHOLD = 10
DEFAULT_CHUNK_SIZE = 5
DEFAULT_OUTPUT_ROOT = Path("output/exports/stock_topic_incremental_analysis_runs")
PROCESSED_STATUSES = ("analyzed", "skipped")


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item or "").strip()]


def recent_cutoff(days: int) -> str:
    return (date.today() - timedelta(days=max(1, int(days)))).isoformat()


def load_pending_stocks(
    *,
    group_id: str,
    pending_threshold: int,
    recent_days: int,
    max_stocks: int = 0,
) -> list[dict[str, Any]]:
    conn = connect()
    try:
        extraction_rows = conn.execute(
            """
            SELECT stock_name, topic_id, topic_date
            FROM zsxq_a_share_topic_stock_extractions
            WHERE group_id = ?
              AND COALESCE(stock_name, '') <> ''
              AND COALESCE(topic_id, '') <> ''
              AND COALESCE(TRIM(excerpt), '') <> ''
              AND topic_date >= ?
            """,
            [group_id, recent_cutoff(recent_days)],
        ).fetchall()
        extracted_by_stock: dict[str, dict[str, Any]] = {}
        for row in extraction_rows:
            stock_name = str(row["stock_name"])
            extracted_by_stock.setdefault(stock_name, {})[str(row["topic_id"])] = row["topic_date"]

        latest_rows = conn.execute(
            """
            SELECT DISTINCT ON (group_id, stock_name)
                   stock_name, topic_ids_json, status,
                   COALESCE(LENGTH(summary_markdown), 0) AS chars,
                   updated_at
            FROM stock_topic_analyses
            WHERE group_id = ?
            ORDER BY group_id, stock_name, updated_at DESC NULLS LAST
            """,
            [group_id],
        ).fetchall()
        latest_by_stock = {str(row["stock_name"]): row for row in latest_rows}

        status_placeholders = ",".join("?" for _ in PROCESSED_STATUSES)
        processed_rows = conn.execute(
            f"""
            SELECT stock_name, topic_id
            FROM stock_topic_processed_states
            WHERE group_id = ?
              AND status IN ({status_placeholders})
            """,
            [group_id, *PROCESSED_STATUSES],
        ).fetchall()
        processed_by_stock: dict[str, set[str]] = {}
        for row in processed_rows:
            processed_by_stock.setdefault(str(row["stock_name"]), set()).add(str(row["topic_id"]))
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    for stock_name, extracted_topics in extracted_by_stock.items():
        latest = latest_by_stock.get(stock_name)
        known_ids = set(processed_by_stock.get(stock_name, set()))
        if latest is not None:
            known_ids.update(parse_json_list(latest["topic_ids_json"]))
        pending_ids = sorted(set(extracted_topics) - known_ids)
        pending_count = len(pending_ids)
        if pending_count <= pending_threshold:
            continue
        items.append(
            {
                "stock": stock_name,
                "pending_topic_count": pending_count,
                "extracted_topic_count": len(extracted_topics),
                "known_topic_count": len(known_ids),
                "has_completed_report": bool(
                    latest
                    and str(latest["status"] or "") == "completed"
                    and int(latest["chars"] or 0) > 0
                ),
                "latest_updated_at": str(latest["updated_at"] or "") if latest else "",
                "pending_topic_ids": pending_ids,
            }
        )

    items.sort(
        key=lambda item: (
            int(item["pending_topic_count"]),
            int(item["extracted_topic_count"]),
            str(item["stock"]),
        ),
        reverse=True,
    )
    if max_stocks > 0:
        return items[:max_stocks]
    return items


def chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    chunk_size = max(1, int(size))
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run stock topic analyses for stocks with incremental topic backlog.")
    parser.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    parser.add_argument("--pending-threshold", type=int, default=DEFAULT_PENDING_THRESHOLD)
    parser.add_argument("--recent-days", type=int, default=365)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--max-stocks", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_root) / run_id
    summary_path = output_dir / "summary.json"
    run_log_path = output_dir / "run.log"

    def log(message: str) -> None:
        line = f"{_now_text()} {message}"
        safe_console_print(line, flush=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        with run_log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    pending = load_pending_stocks(
        group_id=args.group_id,
        pending_threshold=args.pending_threshold,
        recent_days=args.recent_days,
        max_stocks=args.max_stocks,
    )
    summary: dict[str, Any] = {
        "run_id": run_id,
        "group_id": args.group_id,
        "pending_threshold": args.pending_threshold,
        "recent_days": args.recent_days,
        "chunk_size": args.chunk_size,
        "max_stocks": args.max_stocks,
        "dry_run": bool(args.dry_run),
        "selected_stock_count": len(pending),
        "selected_topic_count": sum(int(item["pending_topic_count"]) for item in pending),
        "selected": pending,
        "chunks": [],
        "status": "dry_run" if args.dry_run else "running",
    }
    write_json(summary_path, summary)
    log(
        f"selected_stock_count={summary['selected_stock_count']} "
        f"selected_topic_count={summary['selected_topic_count']} "
        f"pending_topic_count>{args.pending_threshold} recent_days={args.recent_days}"
    )
    if args.dry_run or not pending:
        summary["status"] = "ok"
        write_json(summary_path, summary)
        log("OK no analysis run needed" if not pending else "OK dry run completed")
        return 0

    total_failed = 0
    total_success = 0
    total_no_topics = 0
    aborted = False
    for chunk_index, chunk in enumerate(chunks(pending, args.chunk_size), start=1):
        names = [str(item["stock"]) for item in chunk]
        log(f"chunk={chunk_index} count={len(names)} stocks={names}")
        result = stock_topic_service.analyze_stock_topics_batch(args.group_id, names, log_callback=log)
        batch_summary = result.get("summary") or {}
        chunk_record = {
            "chunk": chunk_index,
            "stocks": names,
            "summary": batch_summary,
        }
        summary["chunks"].append(chunk_record)
        total_success += int(batch_summary.get("success") or 0)
        total_failed += int(batch_summary.get("failed") or 0)
        total_no_topics += int(batch_summary.get("no_topics") or 0)
        if batch_summary.get("aborted"):
            aborted = True
            log(f"WARN chunk aborted: {batch_summary.get('abort_reason') or ''}")
            break
        write_json(summary_path, summary)

    remaining = load_pending_stocks(
        group_id=args.group_id,
        pending_threshold=args.pending_threshold,
        recent_days=args.recent_days,
        max_stocks=0,
    )
    summary.update(
        {
            "status": "fail" if aborted or total_failed else "ok",
            "success_count": total_success,
            "failed_count": total_failed,
            "no_topic_count": total_no_topics,
            "aborted": aborted,
            "remaining_stock_count": len(remaining),
            "remaining_topic_count": sum(int(item["pending_topic_count"]) for item in remaining),
            "remaining": remaining,
        }
    )
    write_json(summary_path, summary)
    log(
        f"{summary['status'].upper()} success={total_success} failed={total_failed} "
        f"no_topics={total_no_topics} remaining_stocks={summary['remaining_stock_count']} "
        f"remaining_topics={summary['remaining_topic_count']} summary={summary_path}"
    )
    return 1 if summary["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
