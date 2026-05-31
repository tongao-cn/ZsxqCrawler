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

from backend.routes.a_share_routes import (
    AShareAnalysisExportTdxRequest,
    AShareAnalysisRunRequest,
    export_a_share_analysis_to_tdx,
    start_a_share_analysis,
)
from backend.routes.crawl_routes import crawl_latest_until_complete
from backend.routes.daily_analysis_routes import DailyAnalysisRequest, create_daily_report
from backend.routes.daily_stock_concept_routes import DailyStockConceptRequest, create_daily_stock_concepts
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
    if task.get("type") == "daily_stock_concepts":
        return (
            f"report_date={result.get('report_date')}, "
            f"topic_count={result.get('topic_count')}, "
            f"stock_count={result.get('stock_count')}, "
            f"concept_count={result.get('concept_count')}, status={result.get('status')}"
        )
    if task.get("type") == "daily_topic_analysis":
        return (
            f"report_date={result.get('report_date')}, "
            f"topic_count={result.get('topic_count')}, "
            f"model={result.get('model')}"
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


async def _create_daily_stock_concept_task(group_id: str, comments_per_topic: int) -> str:
    response = await create_daily_stock_concepts(
        group_id,
        DailyStockConceptRequest(commentsPerTopic=comments_per_topic),
        BackgroundTasks(),
    )
    return response["task_id"]


async def _create_daily_topic_report_task(group_id: str, comments_per_topic: int) -> str:
    response = await create_daily_report(
        group_id,
        DailyAnalysisRequest(commentsPerTopic=comments_per_topic),
        BackgroundTasks(),
    )
    return response["task_id"]


async def _export_tdx(group_id: str, group_name: str | None) -> dict[str, Any]:
    return await export_a_share_analysis_to_tdx(
        AShareAnalysisExportTdxRequest(group_id=group_id, group_name=group_name)
    )


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

    if args.daily_stock_concepts:
        daily_stock_task_id = await _create_daily_stock_concept_task(args.group_id, args.comments_per_topic)
        print(f"daily_stock_concepts_task_id={daily_stock_task_id}")
        daily_stock_task = _wait_task(
            daily_stock_task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.daily_timeout_seconds,
            log_tail=args.log_tail,
        )
        _raise_for_task(daily_stock_task, "daily stock concepts")

    if args.daily_topic_report:
        daily_report_task_id = await _create_daily_topic_report_task(args.group_id, args.comments_per_topic)
        print(f"daily_topic_report_task_id={daily_report_task_id}")
        daily_report_task = _wait_task(
            daily_report_task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.daily_timeout_seconds,
            log_tail=args.log_tail,
        )
        _raise_for_task(daily_report_task, "daily topic report")

    if args.export_tdx:
        tdx_result = await _export_tdx(args.group_id, args.group_name)
        print(f"tdx_export={tdx_result}")

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
    parser.add_argument("--daily-timeout-seconds", type=int, default=2 * 60 * 60)
    parser.add_argument("--comments-per-topic", type=int, default=0)
    parser.add_argument("--daily-stock-concepts", action="store_true")
    parser.add_argument("--daily-topic-report", action="store_true")
    parser.add_argument("--export-tdx", action="store_true")
    parser.add_argument("--group-name", default="纪要又要")
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
