#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.crawl import CrawlSettingsRequest
from backend.services.daily_review_topic_export_service import (
    DEFAULT_GROUP_IDS,
    build_review_topic_export,
    load_review_topics,
    normalize_group_ids,
    normalize_review_slot,
    parse_report_date,
    write_review_topic_export,
)
from backend.services.task_runtime import get_task_logs_state, get_task_state, request_runtime_shutdown
from backend.services.workflow_task_launch import launch_or_reuse_latest_crawl_task


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
SHANGHAI_TZ = timezone(timedelta(hours=8))


def _safe_text(value: Any, encoding: str | None) -> str:
    text = str(value)
    if not encoding:
        return text
    return text.encode(encoding, errors="replace").decode(encoding)


def _safe_print(*values: Any, sep: str = " ", end: str = "\n", file: Any = None, flush: bool = False) -> None:
    stream = file or sys.stdout
    encoding = getattr(stream, "encoding", None)
    text = sep.join(_safe_text(value, encoding) for value in values)
    stream.write(text + end)
    if flush:
        stream.flush()


def _print_log_tail(task_id: str, lines: int) -> None:
    logs = get_task_logs_state(task_id) or []
    if not logs:
        return
    _safe_print(f"--- {task_id} log tail ---")
    for line in logs[-lines:]:
        _safe_print(line)


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    result = task.get("result") or {}
    return {
        "task_id": task.get("task_id"),
        "type": task.get("type"),
        "status": task.get("status"),
        "message": task.get("message"),
        "result": result,
    }


def _wait_task(task_id: str, *, poll_seconds: float, timeout_seconds: int, log_tail: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
    last_status = None
    while True:
        task = get_task_state(task_id)
        if not task:
            raise RuntimeError(f"Task disappeared: {task_id}")

        status = str(task.get("status") or "")
        if status != last_status:
            _safe_print(f"{task_id}: status={status}, message={task.get('message')}")
            last_status = status

        if status in TERMINAL_STATUSES:
            _safe_print(f"{task_id}: final={status}")
            _print_log_tail(task_id, log_tail)
            return task

        if deadline is not None and time.monotonic() > deadline:
            _print_log_tail(task_id, log_tail)
            raise TimeoutError(f"Timed out waiting for task {task_id}")

        time.sleep(poll_seconds)


def _create_or_reuse_crawl_task(group_id: str) -> tuple[str, str]:
    response, source = launch_or_reuse_latest_crawl_task(
        group_id,
        CrawlSettingsRequest(
            topicSource="official",
            crawlIntervalMin=2,
            crawlIntervalMax=5,
            longSleepIntervalMin=180,
            longSleepIntervalMax=300,
            pagesPerBatch=15,
        ),
    )
    return response["task_id"], source


async def _pull_latest_topics(group_ids: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    crawl_results: list[dict[str, Any]] = []
    for group_id in group_ids:
        task_id, source = _create_or_reuse_crawl_task(group_id)
        _safe_print(f"crawl_group={group_id}, task_id={task_id}, source={source}")
        task = _wait_task(
            task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.crawl_timeout_seconds,
            log_tail=args.log_tail,
        )
        crawl_result = _task_summary(task)
        crawl_result["group_id"] = group_id
        crawl_result["source"] = source
        crawl_results.append(crawl_result)
        if task.get("status") != "completed":
            raise RuntimeError(f"crawl task did not complete for group {group_id}: {task.get('status')}")
    return crawl_results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export morning/evening review topics from zsxq_core.")
    parser.add_argument("--slot", required=True, help="morning/early/早报 or evening/post/晚报.")
    parser.add_argument(
        "--group-id",
        action="append",
        default=None,
        help="Group id. Repeat or comma-separate. Defaults to known review-topic groups.",
    )
    parser.add_argument("--date", default=None, help="Report date, YYYY-MM-DD. Defaults to today in Asia/Shanghai.")
    parser.add_argument("--output-dir", default=None, help="Exact output directory. Defaults under output/exports/daily-review-topics.")
    parser.add_argument("--max-topic-chars", type=int, default=8000)
    parser.add_argument("--crawl-latest-first", action="store_true", help="Pull latest topics before exporting.")
    parser.add_argument(
        "--include-prior-evening",
        action="store_true",
        help="When exporting a morning report, also export the previous date's evening report.",
    )
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--crawl-timeout-seconds", type=int, default=0)
    parser.add_argument("--log-tail", type=int, default=20)
    return parser


def _payload_without_topics(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "topics"}


def _build_export_payload(
    *,
    group_ids: list[str],
    report_date: Any,
    slot: Any,
    max_topic_chars: int,
    crawl_results: list[dict[str, Any]],
) -> dict[str, Any]:
    topics = load_review_topics(
        group_ids=group_ids,
        report_date=report_date,
        slot=slot,
        max_topic_chars=max_topic_chars,
    )
    return build_review_topic_export(
        group_ids=group_ids,
        report_date=report_date,
        slot=slot,
        topics=topics,
        crawl_results=crawl_results,
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    slot = normalize_review_slot(args.slot)
    if args.include_prior_evening and slot != "morning":
        raise ValueError("--include-prior-evening is only supported with morning exports")
    group_ids = normalize_group_ids(args.group_id or DEFAULT_GROUP_IDS)
    report_date = parse_report_date(args.date)
    started_at = datetime.now(SHANGHAI_TZ).isoformat()

    crawl_results: list[dict[str, Any]] = []
    if args.crawl_latest_first:
        crawl_results = await _pull_latest_topics(group_ids, args)

    payload = _build_export_payload(
        group_ids=group_ids,
        report_date=report_date,
        slot=slot,
        max_topic_chars=args.max_topic_chars,
        crawl_results=crawl_results,
    )
    payload["started_at"] = started_at

    additional_exports: list[dict[str, Any]] = []
    if args.include_prior_evening:
        prior_evening = _build_export_payload(
            group_ids=group_ids,
            report_date=report_date - timedelta(days=1),
            slot="evening",
            max_topic_chars=args.max_topic_chars,
            crawl_results=crawl_results,
        )
        prior_evening["started_at"] = started_at
        prior_evening["finished_at"] = datetime.now(SHANGHAI_TZ).isoformat()
        prior_evening["output_files"] = write_review_topic_export(prior_evening)
        additional_exports.append(_payload_without_topics(prior_evening))

    payload["additional_exports"] = additional_exports
    payload["finished_at"] = datetime.now(SHANGHAI_TZ).isoformat()
    output_files = write_review_topic_export(payload, args.output_dir)
    payload["output_files"] = output_files
    _safe_print(json.dumps(_payload_without_topics(payload), ensure_ascii=False, indent=2, default=str))
    return payload


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = asyncio.run(_run(args))
    except KeyboardInterrupt:
        request_runtime_shutdown()
        raise
    except Exception as exc:
        _safe_print(str(exc), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
