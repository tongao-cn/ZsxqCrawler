#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes.file_routes import download_files, download_selected_files, sync_files_from_topics
from backend.schemas.files import FileDownloadRequest, FileIdListRequest
from backend.services.file_ai_analysis_entry import create_file_analysis_response
from backend.services.task_runtime import get_task_logs_state, get_task_state, request_runtime_shutdown
from backend.storage.db_compat import connect


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
    file_analyses: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    finished_at: str | None = None
    run_record_path: str | None = None

    def add_task(self, label: str, task: dict[str, Any]) -> None:
        self.tasks.append((label, task))

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        _safe_print(f"WARNING: {message}")

    def add_file_analysis(self, result: dict[str, Any]) -> None:
        self.file_analyses.append(result)

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


def _query_value(group_id: str) -> int | str:
    text = str(group_id or "").strip()
    return int(text) if text.isdigit() else text


def _safe_filename(value: str, limit: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" ._")
    return (name[:limit].strip(" ._") or "file")


def _load_pending_pdf_file_ids(
    *,
    group_id: str,
    start_time: str,
    end_time: str,
    max_files: int | None,
) -> list[int]:
    params: list[Any] = [_query_value(group_id), _query_value(group_id), "%.pdf", "pending"]
    conditions = [
        "f.group_id = ?",
        "t.group_id = ?",
        "lower(f.name) like ?",
        "f.download_status = ?",
        "t.create_time is not null",
        "t.create_time != ''",
    ]
    if len(start_time) == 10 and len(end_time) == 10:
        conditions.append("substr(t.create_time, 1, 10) >= ?")
        conditions.append("substr(t.create_time, 1, 10) <= ?")
    else:
        conditions.append("t.create_time >= ?")
        conditions.append("t.create_time <= ?")
    params.extend([start_time, end_time])

    sql = f"""
        SELECT f.file_id, max(t.create_time) AS latest_topic_create_time
        FROM files f
        JOIN file_topic_relations fr ON fr.file_id = f.file_id
        JOIN topics t ON t.topic_id = fr.topic_id
        WHERE {' AND '.join(conditions)}
        GROUP BY f.file_id
        ORDER BY latest_topic_create_time DESC, f.file_id DESC
    """
    if max_files is not None and max_files > 0:
        sql += " LIMIT ?"
        params.append(int(max_files))

    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return [int(row[0]) for row in cursor.fetchall()]
    finally:
        conn.close()


def _chunks(values: list[int], size: int) -> list[list[int]]:
    chunk_size = max(1, int(size))
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def _load_downloaded_pdf_rows(
    *,
    group_id: str,
    start_time: str,
    end_time: str,
    max_files: int | None,
    pending_any_date: bool,
) -> list[dict[str, Any]]:
    params: list[Any] = [_query_value(group_id), "%.pdf", "completed", "downloaded"]
    conditions = [
        "f.group_id = ?",
        "lower(f.name) like ?",
        "f.download_status in (?, ?)",
    ]
    if pending_any_date:
        conditions.append(
            "(faa.file_id is null or faa.status != ? or faa.summary is null or trim(faa.summary) = '')"
        )
        params.append("completed")
    else:
        conditions.extend(["f.create_time is not null", "f.create_time != ''"])
        if len(start_time) == 10 and len(end_time) == 10:
            conditions.append("substr(f.create_time, 1, 10) >= ?")
            conditions.append("substr(f.create_time, 1, 10) <= ?")
        else:
            conditions.append("f.create_time >= ?")
            conditions.append("f.create_time <= ?")
        params.extend([start_time, end_time])
    sql = f"""
        SELECT f.file_id, f.name, coalesce(f.size, 0), f.create_time, f.download_status, f.local_path
        FROM files f
        LEFT JOIN file_ai_analyses faa ON faa.file_id = f.file_id
        WHERE {' AND '.join(conditions)}
        ORDER BY f.create_time DESC, f.file_id DESC
    """
    if max_files is not None and max_files > 0:
        sql += " LIMIT ?"
        params.append(int(max_files))

    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {
            "file_id": int(row[0]),
            "name": str(row[1] or f"file_{row[0]}.pdf"),
            "size": int(row[2] or 0),
            "create_time": str(row[3] or ""),
            "download_status": str(row[4] or ""),
            "local_path": str(row[5] or ""),
        }
        for row in rows
    ]


def _markdown_output_dir(group_id: str, label: str) -> Path:
    safe_label = _safe_filename(label, limit=40)
    return PROJECT_ROOT / "output" / "exports" / "file_ai_markdown" / str(group_id) / safe_label


def _pdf_analysis_label(args: argparse.Namespace, run_window: tuple[str, str, str]) -> str:
    if args.pdf_analysis_pending_any_date:
        return f"pending-any-date-{_today_text()}"
    return run_window[2]


def _write_file_markdown(output_dir: Path, row: dict[str, Any], analysis: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_id = int(row["file_id"])
    file_name = str(row.get("name") or f"file_{file_id}.pdf")
    output_path = output_dir / f"{file_id}-{_safe_filename(file_name)}.md"
    summary = str(analysis.get("summary") or "").strip()
    body = [
        f"# {file_name}",
        "",
        f"- file_id: `{file_id}`",
        f"- create_time: `{row.get('create_time') or ''}`",
        f"- size: `{row.get('size') or 0}`",
        f"- source_path: `{analysis.get('source_path') or row.get('local_path') or ''}`",
        f"- model: `{analysis.get('model') or ''}`",
        "",
        "## AI Summary",
        "",
        summary or "_No summary returned._",
        "",
    ]
    output_path.write_text("\n".join(body), encoding="utf-8")
    return output_path


def _write_index_markdown(output_dir: Path, group_id: str, label: str, results: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.md"
    lines = [
        f"# PDF AI Summaries - {group_id} - {label}",
        "",
        f"- generated_at: `{datetime.now(SHANGHAI_TZ).isoformat()}`",
        f"- total: `{len(results)}`",
        "",
    ]
    for item in results:
        md_path = item.get("markdown_path") or ""
        name = item.get("name") or f"file_{item.get('file_id')}"
        status = item.get("status") or ""
        rel = Path(md_path).name if md_path else ""
        line = f"- `{status}` [{name}]({rel})" if rel else f"- `{status}` {name}"
        lines.append(line)
    lines.append("")
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def _analyze_pdf_row(
    *,
    group_id: str,
    output_dir: Path,
    row: dict[str, Any],
    index: int,
    total: int,
    force: bool,
) -> dict[str, Any]:
    file_id = int(row["file_id"])
    file_name = str(row["name"])
    try:
        _safe_print(f"[{index}/{total}] analyzing file_id={file_id} name={file_name}")
        response = create_file_analysis_response(group_id, file_id, force=force)
        analysis = response.get("analysis") or {}
        markdown_path = _write_file_markdown(output_dir, row, analysis)
        return {
            "file_id": file_id,
            "name": file_name,
            "status": "completed",
            "cached": bool(analysis.get("cached")),
            "markdown_path": str(markdown_path),
        }
    except Exception as exc:
        _safe_print(f"WARNING: pdf analysis failed file_id={file_id}: {exc}")
        return {
            "file_id": file_id,
            "name": file_name,
            "status": "failed",
            "error": str(exc),
        }


def _analyze_downloaded_pdfs(args: argparse.Namespace, run_window: tuple[str, str, str]) -> list[dict[str, Any]]:
    start_time, end_time, label = run_window
    group_id = args.pdf_analysis_group_id
    rows = _load_downloaded_pdf_rows(
        group_id=group_id,
        start_time=start_time,
        end_time=end_time,
        max_files=args.max_pdf_analyses,
        pending_any_date=args.pdf_analysis_pending_any_date,
    )
    label = _pdf_analysis_label(args, run_window)
    output_dir = _markdown_output_dir(group_id, label)
    results: list[dict[str, Any] | None] = [None] * len(rows)
    max_workers = max(1, int(args.pdf_analysis_concurrency or 1))
    _safe_print(
        f"pdf_analysis_group_id={group_id}, candidate_pdfs={len(rows)}, "
        f"pending_any_date={args.pdf_analysis_pending_any_date}, "
        f"concurrency={max_workers}, output_dir={output_dir}"
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                _analyze_pdf_row,
                group_id=group_id,
                output_dir=output_dir,
                row=row,
                index=index,
                total=len(rows),
                force=args.force_pdf_analysis,
            ): index - 1
            for index, row in enumerate(rows, start=1)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()

    completed_results = [item for item in results if item is not None]
    if completed_results:
        index_path = _write_index_markdown(output_dir, group_id, label, completed_results)
        _safe_print(f"pdf_analysis_index={index_path}")
    return completed_results


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
            "download_pdf_only": args.download_pdf_only,
            "download_concurrency": args.download_concurrency,
            "lookback_hours": args.lookback_hours,
            "download_interval": args.download_interval,
            "long_sleep_interval": args.long_sleep_interval,
            "files_per_batch": args.files_per_batch,
            "download_interval_min": args.download_interval_min,
            "download_interval_max": args.download_interval_max,
            "long_sleep_interval_min": args.long_sleep_interval_min,
            "long_sleep_interval_max": args.long_sleep_interval_max,
            "sync_files_from_topics": args.sync_files_from_topics,
            "analyze_pdf_after_download": args.analyze_pdf_after_download,
            "pdf_analysis_group_id": args.pdf_analysis_group_id,
            "max_pdf_analyses": args.max_pdf_analyses,
            "pdf_analysis_concurrency": args.pdf_analysis_concurrency,
            "pdf_analysis_pending_any_date": args.pdf_analysis_pending_any_date,
            "force_pdf_analysis": args.force_pdf_analysis,
        },
        "tasks": [_record_task(label, task) for label, task in summary.tasks],
        "file_analyses": summary.file_analyses,
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
    if summary.file_analyses:
        completed = sum(1 for item in summary.file_analyses if item.get("status") == "completed")
        failed = sum(1 for item in summary.file_analyses if item.get("status") == "failed")
        _safe_print(f"pdf_analyses: completed={completed}, failed={failed}")
    if summary.warnings:
        _safe_print("warnings:")
        for warning in summary.warnings:
            _safe_print(f"- {warning}")


async def _download_group_files(
    group_id: str,
    args: argparse.Namespace,
    *,
    start_time: str,
    end_time: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    if args.download_pdf_only:
        file_ids = _load_pending_pdf_file_ids(
            group_id=group_id,
            start_time=start_time,
            end_time=end_time,
            max_files=args.max_files_per_group,
        )
        _safe_print(f"group_id={group_id} pending_pdf_files={len(file_ids)}")
        if not file_ids:
            return []
        responses = [
            await download_selected_files(
                group_id,
                FileIdListRequest(file_ids=chunk, concurrency=args.download_concurrency),
            )
            for chunk in _chunks(file_ids, 200)
        ]
    else:
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
        responses = [await download_files(group_id, request)]

    for response in responses:
        download_task_id = response["task_id"]
        _safe_print(f"group_id={group_id} download_files_task_id={download_task_id}")
        tasks.append(
            _wait_task(
                download_task_id,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.task_timeout_seconds,
                log_tail=args.log_tail,
            )
        )
    return tasks


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
                download_tasks = await _download_group_files(
                    group_id,
                    args,
                    start_time=start_time,
                    end_time=end_time,
                )
                for index, download_task in enumerate(download_tasks, start=1):
                    label = f"download files {group_id}"
                    if len(download_tasks) > 1:
                        label = f"{label} batch {index}"
                    summary.add_task(label, download_task)
                    if download_task.get("status") != "completed":
                        summary.warn(f"download files group {group_id} did not complete: {download_task.get('status')}")
            except Exception as exc:
                summary.warn(f"download files group {group_id} failed: {exc}")

        if args.analyze_pdf_after_download:
            for result in _analyze_downloaded_pdfs(args, run_window):
                summary.add_file_analysis(result)
                if result.get("status") == "failed":
                    summary.warn(f"pdf analysis failed file_id={result.get('file_id')}: {result.get('error')}")

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
    parser.add_argument("--download-pdf-only", action="store_true")
    parser.add_argument("--download-concurrency", type=int, default=1)
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
    parser.add_argument("--analyze-pdf-after-download", action="store_true")
    parser.add_argument("--pdf-analysis-group-id", default="51111112855254")
    parser.add_argument("--max-pdf-analyses", type=int, default=50)
    parser.add_argument("--pdf-analysis-concurrency", type=int, default=1)
    parser.add_argument(
        "--pdf-analysis-pending-any-date",
        action="store_true",
        help="Analyze downloaded PDFs from any date that do not already have a completed summary.",
    )
    parser.add_argument("--force-pdf-analysis", action="store_true")
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
