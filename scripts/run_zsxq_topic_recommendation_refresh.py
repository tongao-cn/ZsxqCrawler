#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
from backend.services.a_share_analysis_service import build_chart_payload, normalize_group_id
from backend.services.a_share_research_return_smoke_service import load_knowaction_trade_dates
from backend.services.task_runtime import get_task_logs_state, get_task_state, request_runtime_shutdown
from backend.services.tdx_a_share_export_service import DEFAULT_TDX_EXPORT_SPECS


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


@dataclass
class WorkflowSummary:
    started_at: str = field(default_factory=lambda: datetime.now(SHANGHAI_TZ).isoformat())
    tasks: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    finished_at: str | None = None
    tdx_result: dict[str, Any] | None = None
    tdx_preview: dict[str, Any] | None = None
    tdx_skipped_reason: str | None = None
    run_record_path: str | None = None

    def add_task(self, label: str, task: dict[str, Any]) -> None:
        self.tasks.append((label, task))

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        _safe_print(f"WARNING: {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        _safe_print(f"FAIL: {message}", file=sys.stderr)

    @property
    def level(self) -> str:
        if self.failures:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "OK"


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
    _safe_print(f"--- {task_id} log tail ---")
    for line in logs[-lines:]:
        _safe_print(line)


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
            _safe_print(f"{task_id}: final={status}, {_task_summary(task)}")
            _print_log_tail(task_id, log_tail)
            return task

        if deadline is not None and time.monotonic() > deadline:
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


def _build_tdx_preview(group_id: str, group_name: str | None) -> dict[str, Any]:
    specs = tuple((int(window), int(top_n)) for window, top_n in DEFAULT_TDX_EXPORT_SPECS)
    ranking_windows = tuple(window for window, _top_n in specs)
    ranking_top_n = max(top_n for _window, top_n in specs)
    payload = build_chart_payload(
        group_id=normalize_group_id(group_id),
        top_n=min(ranking_top_n, 100),
        ranking_windows=ranking_windows,
        ranking_top_n=ranking_top_n,
    )
    rankings = payload.get("rankings") or {}
    blocks = []
    for window, top_n in specs:
        rows = rankings.get(str(window)) or []
        candidate_count = min(len(rows), top_n)
        block_name = f"{group_name}-{window}日Top{top_n}" if group_name else f"{window}日Top{top_n}"
        blocks.append(
            {
                "window_days": window,
                "top_n": top_n,
                "candidate_count": candidate_count,
                "block_name": block_name,
            }
        )
    return {
        "selected_start_date": payload.get("selected_start_date"),
        "selected_end_date": payload.get("selected_end_date"),
        "date_count": payload.get("date_count"),
        "total_companies_in_range": payload.get("total_companies_in_range"),
        "total_candidates": sum(block["candidate_count"] for block in blocks),
        "blocks": blocks,
    }


def _tdx_preview_skip_reason(args: argparse.Namespace, preview: dict[str, Any]) -> str | None:
    total_candidates = int(preview.get("total_candidates") or 0)
    if total_candidates < args.tdx_min_preview_total:
        return f"tdx preview total candidates {total_candidates} < minimum {args.tdx_min_preview_total}"
    low_blocks = [
        block
        for block in preview.get("blocks") or []
        if int(block.get("candidate_count") or 0) < args.tdx_min_preview_block_count
    ]
    if low_blocks:
        block_text = ", ".join(
            f"{block.get('window_days')}d={block.get('candidate_count')}" for block in low_blocks
        )
        return f"tdx preview block candidates below minimum {args.tdx_min_preview_block_count}: {block_text}"
    return None


def _print_tdx_preview(preview: dict[str, Any]) -> None:
    blocks = ", ".join(
        f"{block.get('block_name')}={block.get('candidate_count')}"
        for block in preview.get("blocks") or []
    )
    _safe_print(
        "tdx_preview: "
        f"total_candidates={preview.get('total_candidates')}, "
        f"date={preview.get('selected_start_date')}~{preview.get('selected_end_date')}, "
        f"blocks={blocks}"
    )


def _result_int(task: dict[str, Any], key: str) -> int:
    try:
        return int((task.get("result") or {}).get(key) or 0)
    except Exception:
        return 0


def _has_new_recommendation_work(a_share_task: dict[str, Any]) -> bool:
    return _result_int(a_share_task, "added_mentions") > 0 or _result_int(a_share_task, "topic_stock_extractions") > 0


def _is_weekday(now: datetime | None = None) -> bool:
    current = now or datetime.now(SHANGHAI_TZ)
    return current.weekday() < 5


def _is_trade_calendar_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(SHANGHAI_TZ)
    day = current.date()
    return day.isoformat() in load_knowaction_trade_dates(day - timedelta(days=1), day + timedelta(days=1))


def _should_export_tdx(policy: str, summary: WorkflowSummary) -> bool:
    if policy == "always":
        return True
    if policy == "never":
        summary.tdx_skipped_reason = "tdx export policy is never"
        return False
    if policy == "weekday":
        if _is_weekday():
            return True
        summary.tdx_skipped_reason = "today is not a weekday"
        return False
    if policy == "trade-calendar":
        try:
            if _is_trade_calendar_open():
                return True
            summary.tdx_skipped_reason = "today is not open in KnowAction trade_calendar"
            return False
        except Exception as exc:
            summary.warn(f"trade-calendar check failed, falling back to weekday policy: {exc}")
            if _is_weekday():
                return True
            summary.tdx_skipped_reason = "trade-calendar unavailable and today is not a weekday"
            return False
    raise ValueError(f"Unsupported TDX export policy: {policy}")


def _print_health_summary(summary: WorkflowSummary) -> None:
    _safe_print("--- health summary ---")
    _safe_print(f"level={summary.level}")
    for label, task in summary.tasks:
        _safe_print(f"{label}: task_id={task.get('task_id')}, status={task.get('status')}, {_task_summary(task)}")

    if summary.tdx_preview:
        _print_tdx_preview(summary.tdx_preview)

    if summary.tdx_result:
        blocks = summary.tdx_result.get("blocks") or []
        block_text = ", ".join(
            f"{block.get('block_name')}={block.get('written_count')}"
            for block in blocks
        )
        _safe_print(
            "tdx: "
            f"status=exported, total_written={summary.tdx_result.get('total_written')}, "
            f"date={summary.tdx_result.get('selected_start_date')}~{summary.tdx_result.get('selected_end_date')}, "
            f"blocks={block_text}"
        )
    elif summary.tdx_skipped_reason:
        _safe_print(f"tdx: status=skipped, reason={summary.tdx_skipped_reason}")

    if summary.warnings:
        _safe_print("warnings:")
        for warning in summary.warnings:
            _safe_print(f"- {warning}")

    if summary.failures:
        _safe_print("failures:")
        for failure in summary.failures:
            _safe_print(f"- {failure}")


def _record_task(label: str, task: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "task_id": task.get("task_id"),
        "type": task.get("type"),
        "status": task.get("status"),
        "message": task.get("message"),
        "result": task.get("result"),
    }


def _write_run_record(summary: WorkflowSummary, args: argparse.Namespace) -> None:
    summary.finished_at = datetime.now(SHANGHAI_TZ).isoformat()
    run_dir = (
        PROJECT_ROOT
        / "output"
        / "exports"
        / "automation_runs"
        / datetime.now(SHANGHAI_TZ).strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    record_path = run_dir / "summary.json"
    payload = {
        "level": summary.level,
        "started_at": summary.started_at,
        "finished_at": summary.finished_at,
        "args": {
            "group_id": args.group_id,
            "days": args.days,
            "concurrency": args.concurrency,
            "daily_stock_concepts": args.daily_stock_concepts,
            "daily_topic_report": args.daily_topic_report,
            "export_tdx": args.export_tdx,
            "tdx_export_policy": args.tdx_export_policy,
            "skip_tdx_when_no_new_mentions": args.skip_tdx_when_no_new_mentions,
            "tdx_min_preview_total": args.tdx_min_preview_total,
            "tdx_min_preview_block_count": args.tdx_min_preview_block_count,
        },
        "tasks": [_record_task(label, task) for label, task in summary.tasks],
        "warnings": summary.warnings,
        "failures": summary.failures,
        "tdx_preview": summary.tdx_preview,
        "tdx_result": summary.tdx_result,
        "tdx_skipped_reason": summary.tdx_skipped_reason,
    }
    record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary.run_record_path = str(record_path)
    _safe_print(f"run_record={record_path}")


def _finalize(summary: WorkflowSummary, args: argparse.Namespace) -> None:
    _print_health_summary(summary)
    _write_run_record(summary, args)


def _raise_for_task(task: dict[str, Any], label: str) -> None:
    if task.get("status") != "completed":
        raise RuntimeError(f"{label} task did not complete: {task.get('status')} {task.get('message')}")


async def _run(args: argparse.Namespace) -> None:
    summary = WorkflowSummary()
    try:
        _safe_print(f"Refreshing group_id={args.group_id}")
        crawl_task_id = await _create_crawl_task(args.group_id)
        _safe_print(f"crawl_task_id={crawl_task_id}")
        crawl_task = _wait_task(
            crawl_task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.crawl_timeout_seconds,
            log_tail=args.log_tail,
        )
        summary.add_task("crawl", crawl_task)
        _raise_for_task(crawl_task, "crawl")

        a_share_task_id = await _create_a_share_task(args.group_id, args.days, args.concurrency)
        _safe_print(f"a_share_task_id={a_share_task_id}")
        a_share_task = _wait_task(
            a_share_task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.analysis_timeout_seconds,
            log_tail=args.log_tail,
        )
        summary.add_task("a-share", a_share_task)
        _raise_for_task(a_share_task, "a-share")

        if args.daily_stock_concepts:
            try:
                daily_stock_task_id = await _create_daily_stock_concept_task(args.group_id, args.comments_per_topic)
                _safe_print(f"daily_stock_concepts_task_id={daily_stock_task_id}")
                daily_stock_task = _wait_task(
                    daily_stock_task_id,
                    poll_seconds=args.poll_seconds,
                    timeout_seconds=args.daily_timeout_seconds,
                    log_tail=args.log_tail,
                )
                summary.add_task("daily stock concepts", daily_stock_task)
                _raise_for_task(daily_stock_task, "daily stock concepts")
            except Exception as exc:
                summary.warn(f"daily stock concepts failed: {exc}")

        if args.daily_topic_report:
            try:
                daily_report_task_id = await _create_daily_topic_report_task(args.group_id, args.comments_per_topic)
                _safe_print(f"daily_topic_report_task_id={daily_report_task_id}")
                daily_report_task = _wait_task(
                    daily_report_task_id,
                    poll_seconds=args.poll_seconds,
                    timeout_seconds=args.daily_timeout_seconds,
                    log_tail=args.log_tail,
                )
                summary.add_task("daily topic report", daily_report_task)
                _raise_for_task(daily_report_task, "daily topic report")
            except Exception as exc:
                summary.warn(f"daily topic report failed: {exc}")

        if args.export_tdx:
            if args.skip_tdx_when_no_new_mentions and not _has_new_recommendation_work(a_share_task):
                summary.tdx_skipped_reason = "recommendation analysis produced no new mentions or topic extractions"
            elif _should_export_tdx(args.tdx_export_policy, summary):
                try:
                    summary.tdx_preview = _build_tdx_preview(args.group_id, args.group_name)
                    _print_tdx_preview(summary.tdx_preview)
                    preview_skip_reason = _tdx_preview_skip_reason(args, summary.tdx_preview)
                    if preview_skip_reason:
                        summary.tdx_skipped_reason = preview_skip_reason
                        summary.warn(preview_skip_reason)
                    else:
                        summary.tdx_result = await _export_tdx(args.group_id, args.group_name)
                        _safe_print(f"tdx_export={summary.tdx_result}")
                except Exception as exc:
                    summary.warn(f"tdx export failed: {exc}")

        _finalize(summary, args)
        _safe_print("Refresh completed")
    except Exception as exc:
        summary.fail(str(exc))
        _finalize(summary, args)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh latest ZSXQ topics and run the A-share recommendation pool without starting the API server."
    )
    parser.add_argument("--group-id", default="51111112855254")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--crawl-timeout-seconds", type=int, default=0)
    parser.add_argument("--analysis-timeout-seconds", type=int, default=0)
    parser.add_argument("--daily-timeout-seconds", type=int, default=0)
    parser.add_argument("--comments-per-topic", type=int, default=0)
    parser.add_argument("--daily-stock-concepts", action="store_true")
    parser.add_argument("--daily-topic-report", action="store_true")
    parser.add_argument("--export-tdx", action="store_true")
    parser.add_argument("--tdx-export-policy", choices=("always", "weekday", "trade-calendar", "never"), default="weekday")
    parser.add_argument("--skip-tdx-when-no-new-mentions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--tdx-min-preview-total", type=int, default=10)
    parser.add_argument("--tdx-min-preview-block-count", type=int, default=1)
    parser.add_argument("--group-name", default="纪要又要")
    parser.add_argument("--log-tail", type=int, default=20)
    args = parser.parse_args()

    try:
        asyncio.run(_run(args))
    except HTTPException as exc:
        _safe_print(f"HTTP {exc.status_code}: {exc.detail}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        request_runtime_shutdown()
        raise
    except Exception as exc:
        _safe_print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
