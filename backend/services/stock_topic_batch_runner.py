"""Batch scheduling for stock topic analysis."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, List, Tuple


LogCallback = Callable[[str], None] | None
AnalyzeBatchItem = Callable[[int, str], Tuple[Dict[str, Any], str]]

MAX_BATCH_STOCK_ANALYSIS_WORKERS = 10
MAX_BATCH_TRANSIENT_FAILURES = 5
TRANSIENT_BATCH_ERROR_MARKERS = (
    "503",
    "service temporarily unavailable",
    "connection error",
    "timeout",
    "timed out",
)


def _log(log_callback: LogCallback, message: str) -> None:
    if log_callback:
        log_callback(message)


def is_transient_batch_error(message: str) -> bool:
    normalized = str(message or "").strip().lower()
    return any(marker in normalized for marker in TRANSIENT_BATCH_ERROR_MARKERS)


def run_stock_topic_batch(
    *,
    group_id: str,
    stock_names: List[str],
    analyze_one: AnalyzeBatchItem,
    log_callback: LogCallback = None,
    max_workers: int = MAX_BATCH_STOCK_ANALYSIS_WORKERS,
    max_transient_failures: int = MAX_BATCH_TRANSIENT_FAILURES,
    is_transient_error: Callable[[str], bool] = is_transient_batch_error,
) -> Dict[str, Any]:
    total = len(stock_names)
    success_count = 0
    failed_count = 0
    no_topic_count = 0
    consecutive_transient_failures = 0
    abort_reason = ""
    worker_count = min(max_workers, total)
    _log(log_callback, f"开始批量分析，共 {total} 只股票，并发 {worker_count}")
    if total == 0:
        _log(log_callback, "批量分析完成：成功 0，失败 0，无话题 0")
        return {
            "group_id": group_id,
            "stocks": [],
            "summary": {
                "total": 0,
                "success": 0,
                "failed": 0,
                "no_topics": 0,
                "skipped": 0,
                "aborted": False,
                "abort_reason": "",
            },
        }

    def record_result(index: int, result: Dict[str, Any], status: str) -> None:
        nonlocal success_count, failed_count, no_topic_count
        nonlocal consecutive_transient_failures, abort_reason
        ordered_results[index - 1] = result
        if status == "no_topics":
            no_topic_count += 1
            consecutive_transient_failures = 0
        elif status == "failed":
            failed_count += 1
            if is_transient_error(str(result.get("error") or "")):
                consecutive_transient_failures += 1
            else:
                consecutive_transient_failures = 0
        else:
            success_count += 1
            consecutive_transient_failures = 0

        if consecutive_transient_failures >= max_transient_failures and not abort_reason:
            abort_reason = f"连续 {consecutive_transient_failures} 个临时错误，停止提交后续股票"
            _log(log_callback, f"⚠️ {abort_reason}")

    ordered_results: List[Dict[str, Any] | None] = [None] * total
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        next_position = 1

        def submit_next() -> None:
            nonlocal next_position
            if next_position > total:
                return
            futures[
                executor.submit(analyze_one, next_position, stock_names[next_position - 1])
            ] = next_position
            next_position += 1

        for _ in range(worker_count):
            submit_next()

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                index = futures.pop(future, None)
                if index is None:
                    continue
                result, status = future.result()
                record_result(index, result, status)
                if not abort_reason:
                    submit_next()

    results = [result for result in ordered_results if result is not None]
    skipped_count = total - len(results)
    if abort_reason:
        _log(
            log_callback,
            f"批量分析中止：成功 {success_count}，失败 {failed_count}，无话题 {no_topic_count}，未提交 {skipped_count}",
        )
    else:
        _log(
            log_callback,
            f"批量分析完成：成功 {success_count}，失败 {failed_count}，无话题 {no_topic_count}",
        )
    return {
        "group_id": group_id,
        "stocks": results,
        "summary": {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "no_topics": no_topic_count,
            "skipped": skipped_count,
            "aborted": bool(abort_reason),
            "abort_reason": abort_reason,
        },
    }
