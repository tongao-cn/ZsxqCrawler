#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes.a_share_routes import AShareAnalysisRunRequest, start_a_share_analysis
from backend.routes.crawl_routes import crawl_latest_until_complete
from backend.schemas.crawl import CrawlSettingsRequest
from backend.services.task_runtime import get_task_logs_state, get_task_state, request_runtime_shutdown


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _task_summary(task: dict[str, Any]) -> str:
    result = task.get("result") or {}
    if task.get("type") == "crawl_latest_until_complete":
        return (
            f"new_topics={result.get('new_topics')}, "
            f"updated_topics={result.get('updated_topics')}, "
            f"errors={result.get('errors')}, pages={result.get('pages')}"
        )
    if task.get("type") == "a_share_analysis":
        return (
            f"items_processed={result.get('items_processed')}, "
            f"items_succeeded={result.get('items_succeeded')}, "
            f"items_failed={result.get('items_failed')}, "
            f"added_mentions={result.get('added_mentions')}, "
            f"topic_stock_extractions={result.get('topic_stock_extractions')}"
        )
    return str(result)


def _print_log_tail(task_id: str, lines: int) -> None:
    logs = get_task_logs_state(task_id) or []
    if not logs:
        return
    print(f"--- {task_id} log tail ---")
    for line in logs[-lines:]:
        print(line)


def _wait_task(task_id: str, *, poll_seconds: float, timeout_seconds: int, log_tail: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while True:
        task = get_task_state(task_id)
        if not task:
            raise RuntimeError(f"Task disappeared: {task_id}")

        status = str(task.get("status") or "")
        if status != last_status:
            print(f"{task_id}: status={status}, message={task.get('message')}")
            last_status = status

        if status in TERMINAL_STATUSES:
            print(f"{task_id}: final={status}, {_task_summary(task)}")
            _print_log_tail(task_id, log_tail)
            return task

        if time.monotonic() > deadline:
            _print_log_tail(task_id, log_tail)
            raise TimeoutError(f"Timed out waiting for task {task_id}")

        time.sleep(poll_seconds)


async def _create_crawl_task(group_id: str) -> str:
    response = await crawl_latest_until_complete(
        group_id,
        CrawlSettingsRequest(
            topicSource="official",
            crawlIntervalMin=2,
            crawlIntervalMax=5,
            longSleepIntervalMin=180,
            longSleepIntervalMax=300,
            pagesPerBatch=15,
        ),
        BackgroundTasks(),
    )
    return response["task_id"]


async def _create_a_share_task(group_id: str, days: int, concurrency: int) -> str:
    response = await start_a_share_analysis(
        AShareAnalysisRunRequest(group_id=group_id, days=days, concurrency=concurrency),
        BackgroundTasks(),
    )
    return response["task_id"]


def _raise_for_task(task: dict[str, Any], label: str) -> None:
    if task.get("status") != "completed":
        raise RuntimeError(f"{label} task did not complete: {task.get('status')} {task.get('message')}")


async def _run(args: argparse.Namespace) -> None:
    print(f"Refreshing group_id={args.group_id}")
    crawl_task_id = await _create_crawl_task(args.group_id)
    print(f"crawl_task_id={crawl_task_id}")
    crawl_task = _wait_task(
        crawl_task_id,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.crawl_timeout_seconds,
        log_tail=args.log_tail,
    )
    _raise_for_task(crawl_task, "crawl")

    a_share_task_id = await _create_a_share_task(args.group_id, args.days, args.concurrency)
    print(f"a_share_task_id={a_share_task_id}")
    a_share_task = _wait_task(
        a_share_task_id,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.analysis_timeout_seconds,
        log_tail=args.log_tail,
    )
    _raise_for_task(a_share_task, "a-share")

    print("Refresh completed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh latest ZSXQ topics and run the A-share recommendation pool without starting the API server."
    )
    parser.add_argument("--group-id", default="51111112855254")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--crawl-timeout-seconds", type=int, default=30 * 60)
    parser.add_argument("--analysis-timeout-seconds", type=int, default=3 * 60 * 60)
    parser.add_argument("--log-tail", type=int, default=20)
    args = parser.parse_args()

    try:
        asyncio.run(_run(args))
    except HTTPException as exc:
        print(f"HTTP {exc.status_code}: {exc.detail}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        request_runtime_shutdown()
        raise
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
