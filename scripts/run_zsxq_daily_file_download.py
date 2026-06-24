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

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes.file_routes import download_files, sync_files_from_topics
from backend.schemas.files import FileDownloadRequest
from backend.services.task_runtime import get_task_logs_state, get_task_state, request_runtime_shutdown


DEFAULT_GROUP_IDS = ("51111112855254", "28888222124181", "15552822451452")
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
    finished_at: str | None = None
    run_record_path: str | None = None

    def add_task(self, label: str, task: dict[str, Any]) -> None:
        self.tasks.append((label, task))

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        _safe_print(f"WARNING: {message}")

    @property
    def level(self) -> str:
        return "WARN" if self.warnings else "OK"


def _today_text() -> str:
    return datetime.now(SHANGHAI_TZ).date().isoformat()


def _format_zsxq_time(value: datetime) -> str:
    return value.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def _download_window(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.lookback_hours:
        end_dt = datetime.now(SHANGHAI_TZ)
        start_dt = end_dt - timedelta(hours=args.lookback_hours)
        return (
            _format_zsxq_time(start_dt),
            _format_zsxq_time(end_dt),
            f"last {args.lookback_hours} hours",
        )
    run_date = args.date or _today_text()
    return run_date, run_date, run_date


def _group_ids(args: argparse.Namespace) -> list[str]:
    seen: set[str] = set()
    group_ids: list[str] = []
    raw_values = args.group_id or list(DEFAULT_GROUP_IDS)
    for raw_value in raw_values:
        for group_id in str(raw_value or "").split(","):
            normalized = group_id.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            group_ids.append(normalized)
    return group_ids


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
            _safe_print(f"{task_id}: final={status}, result={task.get('result')}")
            _print_log_tail(task_id, log_tail)
            return task

        if deadline is not None and time.monotonic() > deadline:
            _print_log_tail(task_id, log_tail)
            raise TimeoutError(f"Timed out waiting for task {task_id}")

        time.sleep(poll_seconds)


def _record_task(label: str, task: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "task_id": task.get("task_id"),
        "type": task.get("type"),
        "status": task.get("status"),
        "message": task.get("message"),
        "result": task.get("result"),
    }


def _write_run_record(summary: WorkflowSummary, args: argparse.Namespace, run_window: tuple[str, str, str]) -> None:
    summary.finished_at = datetime.now(SHANGHAI_TZ).isoformat()
    run_dir = (
        PROJECT_ROOT
        / "output"
        / "exports"
        / "daily_file_download_runs"
        / datetime.now(SHANGHAI_TZ).strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    record_path = run_dir / "summary.json"
    start_time, end_time, label = run_window
    payload = {
        "level": summary.level,
        "started_at": summary.started_at,
        "finished_at": summary.finished_at,
        "run_date": label,
        "run_window": {
            "start_time": start_time,
            "end_time": end_time,
            "label": label,
        },
        "args": {
            "group_ids": _group_ids(args),
            "max_files_per_group": args.max_files_per_group,
            "lookback_hours": args.lookback_hours,
            "download_interval": args.download_interval,
            "long_sleep_interval": args.long_sleep_interval,
            "files_per_batch": args.files_per_batch,
            "download_interval_min": args.download_interval_min,
            "download_interval_max": args.download_interval_max,
            "long_sleep_interval_min": args.long_sleep_interval_min,
            "long_sleep_interval_max": args.long_sleep_interval_max,
            "sync_files_from_topics": args.sync_files_from_topics,
        },
        "tasks": [_record_task(label, task) for label, task in summary.tasks],
        "warnings": summary.warnings,
    }
    record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary.run_record_path = str(record_path)
    _safe_print(f"run_record={record_path}")


def _print_health_summary(summary: WorkflowSummary) -> None:
    _safe_print("--- health summary ---")
    _safe_print(f"level={summary.level}")
    for label, task in summary.tasks:
        _safe_print(f"{label}: task_id={task.get('task_id')}, status={task.get('status')}, result={task.get('result')}")
    if summary.warnings:
        _safe_print("warnings:")
        for warning in summary.warnings:
            _safe_print(f"- {warning}")


async def _run(args: argparse.Namespace) -> None:
    run_window = _download_window(args)
    start_time, end_time, _ = run_window
    summary = WorkflowSummary()
    try:
        for group_id in _group_ids(args):
            if args.sync_files_from_topics:
                try:
                    sync_response = await sync_files_from_topics(group_id)
                    sync_task_id = sync_response["task_id"]
                    _safe_print(f"group_id={group_id} sync_files_task_id={sync_task_id}")
                    sync_task = _wait_task(
                        sync_task_id,
                        poll_seconds=args.poll_seconds,
                        timeout_seconds=args.task_timeout_seconds,
                        log_tail=args.log_tail,
                    )
                    summary.add_task(f"sync files {group_id}", sync_task)
                    if sync_task.get("status") != "completed":
                        summary.warn(f"sync files group {group_id} did not complete: {sync_task.get('status')}")
                except Exception as exc:
                    summary.warn(f"sync files group {group_id} failed: {exc}")

            try:
                request = FileDownloadRequest(
                    max_files=args.max_files_per_group,
                    sort_by="create_time",
                    start_time=start_time,
                    end_time=end_time,
                    download_interval=args.download_interval,
                    long_sleep_interval=args.long_sleep_interval,
                    files_per_batch=args.files_per_batch,
                    download_interval_min=args.download_interval_min,
                    download_interval_max=args.download_interval_max,
                    long_sleep_interval_min=args.long_sleep_interval_min,
                    long_sleep_interval_max=args.long_sleep_interval_max,
                )
                download_response = await download_files(group_id, request)
                download_task_id = download_response["task_id"]
                _safe_print(f"group_id={group_id} download_files_task_id={download_task_id}")
                download_task = _wait_task(
                    download_task_id,
                    poll_seconds=args.poll_seconds,
                    timeout_seconds=args.task_timeout_seconds,
                    log_tail=args.log_tail,
                )
                summary.add_task(f"download files {group_id}", download_task)
                if download_task.get("status") != "completed":
                    summary.warn(f"download files group {group_id} did not complete: {download_task.get('status')}")
            except Exception as exc:
                summary.warn(f"download files group {group_id} failed: {exc}")

        _print_health_summary(summary)
        _write_run_record(summary, args, run_window)
    except Exception as exc:
        summary.warn(str(exc))
        _print_health_summary(summary)
        _write_run_record(summary, args, run_window)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Download today's ZSXQ files for configured groups.")
    parser.add_argument("--group-id", action="append", default=[])
    parser.add_argument("--date", help="Date to download, YYYY-MM-DD. Defaults to today in Asia/Shanghai.")
    parser.add_argument("--lookback-hours", type=int, help="Download files created in the last N hours.")
    parser.add_argument("--max-files-per-group", type=int)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--task-timeout-seconds", type=int, default=0)
    parser.add_argument("--download-interval", type=float, default=2.0)
    parser.add_argument("--long-sleep-interval", type=float, default=90.0)
    parser.add_argument("--files-per-batch", type=int, default=10)
    parser.add_argument("--download-interval-min", type=float, default=2.0)
    parser.add_argument("--download-interval-max", type=float, default=5.0)
    parser.add_argument("--long-sleep-interval-min", type=float, default=90.0)
    parser.add_argument("--long-sleep-interval-max", type=float, default=180.0)
    parser.add_argument("--sync-files-from-topics", action=argparse.BooleanOptionalAction, default=True)
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
