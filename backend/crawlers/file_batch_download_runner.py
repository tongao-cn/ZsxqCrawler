"""Batch file download runner for ZSXQ file downloads."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Protocol

from backend.crawlers.file_list_page import file_list_page
from backend.crawlers.zsxq_file_downloader_helpers import (
    batch_download_completion_messages,
    batch_download_empty_page_message,
    batch_download_fetch_failed_message,
    batch_download_file_stop_message,
    batch_download_initial_stop_message,
    batch_download_item_message,
    batch_download_loop_stop_message,
    batch_download_next_page_plan,
    batch_download_page_files_message,
    batch_download_skipped_message,
    batch_download_start_messages,
    download_result_stats,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    BatchDownloadFetchTarget,
    BatchDownloadFileItemTarget,
    BatchDownloadLoopStep,
    BatchDownloadLoopTarget,
    BatchDownloadNextIndexTarget,
    BatchDownloadPage,
    BatchDownloadPageFilesTarget,
    BatchDownloadPageRunTarget,
    BatchDownloadResultTarget,
    BatchDownloadTarget,
)


class BatchDownloadRuntime(Protocol):
    def log(self, message: str) -> None:
        ...

    def check_stop(self) -> bool:
        ...

    def fetch_file_list(self, **kwargs: Any) -> Any:
        ...

    def download_file(self, file_info: Dict[str, Any]) -> Any:
        ...

    def check_long_delay(self) -> Any:
        ...

    def download_delay(self) -> Any:
        ...


def record_file_download_result(result: Any, stats: Dict[str, int]) -> str:
    if result == "skipped":
        stats["skipped"] += 1
        return "skipped"
    if result:
        stats["downloaded"] += 1
        return "downloaded"
    stats["failed"] += 1
    return "failed"


def batch_download_file_name(file_info: Dict[str, Any]) -> Any:
    file_data = file_info.get("file", {})
    return file_data.get("name", "Unknown")


def download_batch_file_item_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadFileItemTarget,
) -> int:
    log_batch_download_file_item(runtime, target)
    result = runtime.download_file(target.file_info)
    downloaded_in_batch = apply_batch_file_item_result(runtime, target, result)
    record_batch_file_item_attempt(target.stats)
    return downloaded_in_batch


def log_batch_download_file_item(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadFileItemTarget,
) -> None:
    file_name = batch_download_file_name(target.file_info)
    runtime.log(batch_download_item_message(target.item_number, target.max_files, file_name))


def apply_batch_file_item_result(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadFileItemTarget,
    result: Any,
) -> int:
    return apply_batch_download_result_target(
        runtime,
        BatchDownloadResultTarget(
            result,
            target.has_more_in_batch,
            target.downloaded_in_batch,
            target.max_files,
            target.stats,
        ),
    )


def record_batch_file_item_attempt(stats: Dict[str, int]) -> None:
    stats["total_files"] += 1


def apply_batch_download_result(
    runtime: BatchDownloadRuntime,
    result: Any,
    has_more_in_batch: bool,
    downloaded_in_batch: int,
    max_files: Optional[int],
    stats: Dict[str, int],
) -> int:
    return apply_batch_download_result_target(
        runtime,
        BatchDownloadResultTarget(
            result,
            has_more_in_batch,
            downloaded_in_batch,
            max_files,
            stats,
        ),
    )


def apply_batch_download_result_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadResultTarget,
) -> int:
    downloaded_in_batch = target.downloaded_in_batch
    result_status = record_file_download_result(target.result, target.stats)
    if result_status == "skipped":
        log_batch_download_skipped(runtime)
    elif result_status == "downloaded":
        downloaded_in_batch = apply_successful_batch_download_result(
            runtime,
            target,
            downloaded_in_batch,
        )

    return downloaded_in_batch


def log_batch_download_skipped(runtime: BatchDownloadRuntime) -> None:
    runtime.log(batch_download_skipped_message())


def apply_successful_batch_download_result(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadResultTarget,
    downloaded_in_batch: int,
) -> int:
    downloaded_in_batch += 1
    runtime.check_long_delay()
    if should_delay_after_batch_download(target, downloaded_in_batch):
        runtime.download_delay()
    return downloaded_in_batch


def should_delay_after_batch_download(
    target: BatchDownloadResultTarget,
    downloaded_in_batch: int,
) -> bool:
    not_reached_limit = target.max_files is None or downloaded_in_batch < target.max_files
    return target.has_more_in_batch and not_reached_limit


def next_batch_download_index_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadNextIndexTarget,
) -> Optional[str]:
    next_page = runtime._batch_download_next_page_plan_for_target(target)  # type: ignore[attr-defined]
    return runtime._apply_batch_download_next_page(next_page)  # type: ignore[attr-defined]


def batch_download_next_page_plan_for_target(
    target: BatchDownloadNextIndexTarget,
) -> Dict[str, Any]:
    return batch_download_next_page_plan(
        target.next_index,
        target.downloaded_in_batch,
        target.max_files,
    )


def apply_batch_download_next_page(
    runtime: BatchDownloadRuntime,
    next_page: Dict[str, Any],
) -> Optional[str]:
    if not next_page["should_continue"]:
        return None

    runtime.log(next_page["message"])
    time.sleep(next_page["delay"])
    return next_page["next_index"]


def download_batch_page_files_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageFilesTarget,
) -> int:
    downloaded_in_batch = target.downloaded_in_batch

    for i, file_info in enumerate(target.files):
        if runtime._is_batch_page_file_download_stopped():  # type: ignore[attr-defined]
            break

        if runtime._has_reached_batch_page_file_download_limit(target, downloaded_in_batch):  # type: ignore[attr-defined]
            break

        downloaded_in_batch = runtime._download_batch_page_file_for_target(  # type: ignore[attr-defined]
            target,
            file_info,
            i,
            downloaded_in_batch,
        )

    return downloaded_in_batch


def is_batch_page_file_download_stopped(runtime: BatchDownloadRuntime) -> bool:
    if not runtime.check_stop():
        return False

    runtime.log(batch_download_file_stop_message())
    return True


def has_reached_batch_page_file_download_limit(
    target: BatchDownloadPageFilesTarget,
    downloaded_in_batch: int,
) -> bool:
    return target.max_files is not None and downloaded_in_batch >= target.max_files


def download_batch_page_file_for_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageFilesTarget,
    file_info: Dict[str, Any],
    file_index: int,
    downloaded_in_batch: int,
) -> int:
    return runtime._download_batch_file_item_target(  # type: ignore[attr-defined]
        runtime._batch_page_file_item_target(  # type: ignore[attr-defined]
            target,
            file_info,
            file_index,
            downloaded_in_batch,
        ),
    )


def batch_page_file_item_target(
    target: BatchDownloadPageFilesTarget,
    file_info: Dict[str, Any],
    file_index: int,
    downloaded_in_batch: int,
) -> BatchDownloadFileItemTarget:
    return BatchDownloadFileItemTarget(
        file_info,
        downloaded_in_batch + 1,
        target.max_files,
        (file_index + 1) < len(target.files),
        downloaded_in_batch,
        target.stats,
    )


def fetch_batch_download_page_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadFetchTarget,
) -> Optional[BatchDownloadPage]:
    data = runtime._fetch_batch_download_page_data(target)  # type: ignore[attr-defined]
    if not data:
        return runtime._handle_batch_download_page_fetch_failure()  # type: ignore[attr-defined]

    return runtime._batch_download_page_from_response(data)  # type: ignore[attr-defined]


def fetch_batch_download_page_data(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadFetchTarget,
) -> Optional[Dict[str, Any]]:
    return runtime.fetch_file_list(count=20, index=target.current_index)


def handle_batch_download_page_fetch_failure(
    runtime: BatchDownloadRuntime,
) -> Optional[BatchDownloadPage]:
    runtime.log(batch_download_fetch_failed_message())
    return None


def batch_download_page_from_response(
    runtime: BatchDownloadRuntime,
    data: Dict[str, Any],
) -> Optional[BatchDownloadPage]:
    page = file_list_page(data)

    if not page.files:
        return runtime._handle_empty_batch_download_page()  # type: ignore[attr-defined]

    runtime.log(batch_download_page_files_message(len(page.files)))
    return BatchDownloadPage(page.files, page.next_index)


def handle_empty_batch_download_page(runtime: BatchDownloadRuntime) -> Optional[BatchDownloadPage]:
    runtime.log(batch_download_empty_page_message())
    return None


def run_batch_download_page_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageRunTarget,
) -> Optional[BatchDownloadLoopStep]:
    page = runtime._fetch_batch_download_page_for_run_target(target)  # type: ignore[attr-defined]
    if page is None:
        return None

    return runtime._batch_download_loop_step_from_page(target, page)  # type: ignore[attr-defined]


def batch_download_loop_step_from_page(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageRunTarget,
    page: BatchDownloadPage,
) -> BatchDownloadLoopStep:
    downloaded_in_batch = runtime._download_batch_page_files_for_run_target(target, page)  # type: ignore[attr-defined]

    next_index = runtime._next_batch_download_index_for_run_target(  # type: ignore[attr-defined]
        target,
        page,
        downloaded_in_batch,
    )
    return BatchDownloadLoopStep(downloaded_in_batch, next_index)


def fetch_batch_download_page_for_run_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageRunTarget,
) -> Optional[BatchDownloadPage]:
    return runtime._fetch_batch_download_page_target(  # type: ignore[attr-defined]
        BatchDownloadFetchTarget(target.step.next_index),
    )


def download_batch_page_files_for_run_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageRunTarget,
    page: BatchDownloadPage,
) -> int:
    return runtime._download_batch_page_files_target(  # type: ignore[attr-defined]
        runtime._batch_page_files_target_for_page(target, page),  # type: ignore[attr-defined]
    )


def next_batch_download_index_for_run_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadPageRunTarget,
    page: BatchDownloadPage,
    downloaded_in_batch: int,
) -> Optional[str]:
    return runtime._next_batch_download_index_target(  # type: ignore[attr-defined]
        BatchDownloadNextIndexTarget(
            page.next_index,
            downloaded_in_batch,
            target.max_files,
        ),
    )


def batch_page_files_target_for_page(
    target: BatchDownloadPageRunTarget,
    page: BatchDownloadPage,
) -> BatchDownloadPageFilesTarget:
    return BatchDownloadPageFilesTarget(
        page.files,
        target.step.downloaded_in_batch,
        target.max_files,
        target.stats,
    )


def run_batch_download_loop_target(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadLoopTarget,
) -> None:
    step = runtime._initial_batch_download_loop_step(target)  # type: ignore[attr-defined]

    while runtime._should_continue_batch_download_loop(target, step):  # type: ignore[attr-defined]
        step = runtime._run_batch_download_loop_iteration(target, step)  # type: ignore[attr-defined]
        if step is None:
            break


def should_continue_batch_download_loop(
    target: BatchDownloadLoopTarget,
    step: BatchDownloadLoopStep,
) -> bool:
    return target.max_files is None or step.downloaded_in_batch < target.max_files


def run_batch_download_loop_iteration(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadLoopTarget,
    step: BatchDownloadLoopStep,
) -> Optional[BatchDownloadLoopStep]:
    if runtime._is_batch_download_loop_stopped():  # type: ignore[attr-defined]
        return None

    next_step = runtime._advance_batch_download_loop_step(target, step)  # type: ignore[attr-defined]
    if next_step is None:
        return None

    if runtime._is_terminal_batch_download_loop_step(next_step):  # type: ignore[attr-defined]
        return None

    return next_step


def is_batch_download_loop_stopped(runtime: BatchDownloadRuntime) -> bool:
    if not runtime.check_stop():
        return False

    runtime.log(batch_download_loop_stop_message())
    return True


def run_next_batch_download_loop_step(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadLoopTarget,
    step: BatchDownloadLoopStep,
) -> Optional[BatchDownloadLoopStep]:
    return runtime._run_batch_download_page_target(  # type: ignore[attr-defined]
        BatchDownloadPageRunTarget(step, target.max_files, target.stats),
    )


def advance_batch_download_loop_step(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadLoopTarget,
    step: BatchDownloadLoopStep,
) -> Optional[BatchDownloadLoopStep]:
    next_step = runtime._run_next_batch_download_loop_step(target, step)  # type: ignore[attr-defined]
    if runtime._is_missing_batch_download_loop_step(next_step):  # type: ignore[attr-defined]
        return None

    return next_step


def is_missing_batch_download_loop_step(step: Optional[BatchDownloadLoopStep]) -> bool:
    return step is None


def is_terminal_batch_download_loop_step(step: BatchDownloadLoopStep) -> bool:
    return step.next_index is None


def initial_batch_download_loop_step(target: BatchDownloadLoopTarget) -> BatchDownloadLoopStep:
    return BatchDownloadLoopStep(0, target.start_index)


def run_batch_file_download(
    runtime: BatchDownloadRuntime,
    target: BatchDownloadTarget,
) -> Dict[str, int]:
    runtime._log_batch_download_start(target.max_files)  # type: ignore[attr-defined]

    if runtime._is_initial_batch_download_stopped():  # type: ignore[attr-defined]
        return download_result_stats()

    stats = download_result_stats()
    runtime._run_batch_download_loop_target(  # type: ignore[attr-defined]
        BatchDownloadLoopTarget(stats, target.max_files, target.start_index),
    )

    runtime._log_batch_download_completion(stats)  # type: ignore[attr-defined]

    return stats


def is_initial_batch_download_stopped(runtime: BatchDownloadRuntime) -> bool:
    if not runtime.check_stop():
        return False

    runtime.log(batch_download_initial_stop_message())
    return True


def log_batch_download_start(runtime: BatchDownloadRuntime, max_files: Optional[int]) -> None:
    for message in batch_download_start_messages(max_files):
        runtime.log(message)


def log_batch_download_completion(runtime: BatchDownloadRuntime, stats: Dict[str, int]) -> None:
    for message in batch_download_completion_messages(stats):
        runtime.log(message)
