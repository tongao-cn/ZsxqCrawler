"""Download outcome side-effect runner for ZSXQ file downloads."""

from __future__ import annotations

import os
from typing import Any, Optional, Protocol, Tuple

from backend.crawlers.file_download_transfer import (
    DownloadCompletionTarget,
    DownloadExceptionTarget,
    DownloadFailureDetail,
    DownloadHttpFailureTarget,
    DownloadSizeMismatchTarget,
)
from backend.crawlers.file_download_policy import (
    download_exception_detail,
    download_final_failure_detail,
    download_http_failure_detail,
    download_size_mismatch_detail,
    download_url_failure_detail,
    partial_download_path,
    remove_partial_download,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    DownloadFinalFailureTarget,
    DownloadStopTarget,
    DownloadUrlUnavailableTarget,
)


class DownloadOutcomeRuntime(Protocol):
    file_db: Any
    download_count: int
    current_batch_count: int

    def log(self, message: str) -> None:
        ...

    def _apply_download_intervals(self) -> None:
        ...


def mark_download_url_unavailable_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadUrlUnavailableTarget,
) -> None:
    runtime.log("   ❌ 无法获取下载链接")
    failure_detail = download_url_unavailable_failure_detail(target)
    update_download_url_unavailable_status(runtime, target.file_id, failure_detail)


def download_url_unavailable_failure_detail(
    target: DownloadUrlUnavailableTarget,
) -> DownloadFailureDetail:
    error_code, error_message = download_url_failure_detail(target.last_download_url_error)
    return DownloadFailureDetail(error_code, error_message)


def update_download_url_unavailable_status(
    runtime: DownloadOutcomeRuntime,
    file_id: int,
    failure_detail: DownloadFailureDetail,
) -> None:
    runtime.file_db.update_file_download_status(
        file_id,
        "failed",
        error_code=failure_detail.error_code,
        error_message=failure_detail.error_message,
    )


def mark_download_failed_after_retries_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadFinalFailureTarget,
) -> None:
    runtime.log(f"   🚫 文件下载重试{target.download_retries}次仍失败: {target.last_error}")
    failure_detail = download_final_failure_detail_for_target(target)
    update_download_final_failure_status(runtime, target.file_id, failure_detail)


def download_final_failure_detail_for_target(
    target: DownloadFinalFailureTarget,
) -> DownloadFailureDetail:
    error_code, error_message = download_final_failure_detail(
        target.last_error_code,
        target.last_error,
    )
    return DownloadFailureDetail(error_code, error_message)


def update_download_final_failure_status(
    runtime: DownloadOutcomeRuntime,
    file_id: int,
    failure_detail: DownloadFailureDetail,
) -> None:
    runtime.file_db.update_file_download_status(
        file_id,
        "failed",
        error_code=failure_detail.error_code,
        error_message=failure_detail.error_message,
    )


def complete_successful_download_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadCompletionTarget,
) -> None:
    replace_successful_download_file(target)
    log_successful_download_target(runtime, target)
    mark_successful_download_completed(runtime, target)
    increment_successful_download_counters(runtime)
    runtime._apply_download_intervals()


def replace_successful_download_file(target: DownloadCompletionTarget) -> None:
    os.replace(target.temp_path, target.file_path)


def log_successful_download_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadCompletionTarget,
) -> None:
    runtime.log(f"   ✅ 下载完成: {target.safe_filename}")
    runtime.log(f"   💾 保存路径: {target.file_path}")


def mark_successful_download_completed(
    runtime: DownloadOutcomeRuntime,
    target: DownloadCompletionTarget,
) -> None:
    runtime.file_db.update_file_download_status(
        target.file_id,
        "completed",
        target.file_path,
    )


def increment_successful_download_counters(runtime: DownloadOutcomeRuntime) -> None:
    runtime.download_count += 1
    runtime.current_batch_count += 1


def record_download_http_failure_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadHttpFailureTarget,
) -> DownloadFailureDetail:
    error_code, error_message = download_http_failure_detail_for_target(target)
    log_download_http_failure(runtime, error_message)
    return DownloadFailureDetail(error_code, error_message)


def download_http_failure_detail_for_target(
    target: DownloadHttpFailureTarget,
) -> Tuple[str, str]:
    return download_http_failure_detail(target.status_code)


def log_download_http_failure(runtime: DownloadOutcomeRuntime, error_message: str) -> None:
    runtime.log(f"   ❌ 下载失败: {error_message}")


def record_download_exception_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadExceptionTarget,
) -> DownloadFailureDetail:
    error_code, error_message = download_exception_detail_for_target(target)
    log_download_exception(runtime, target.exc)
    remove_partial_download_after_exception(runtime, target.file_path)
    return DownloadFailureDetail(error_code, error_message)


def download_exception_detail_for_target(
    target: DownloadExceptionTarget,
) -> Tuple[str, str]:
    return download_exception_detail(target.exc)


def log_download_exception(runtime: DownloadOutcomeRuntime, exc: Exception) -> None:
    runtime.log(f"   ❌ 下载异常: {exc}")


def remove_partial_download_after_exception(
    runtime: DownloadOutcomeRuntime,
    file_path: str,
) -> None:
    temp_path = partial_download_path(file_path)
    if remove_partial_download(temp_path):
        runtime.log("   🗑️ 删除不完整文件")


def handle_download_size_mismatch_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadSizeMismatchTarget,
) -> Optional[DownloadFailureDetail]:
    raw_mismatch_detail = raw_download_size_mismatch_detail_for_target(target)
    if not raw_mismatch_detail:
        return None

    return download_size_mismatch_failure_detail(runtime, target, raw_mismatch_detail)


def raw_download_size_mismatch_detail_for_target(
    target: DownloadSizeMismatchTarget,
) -> Optional[Tuple[str, str]]:
    final_size = os.path.getsize(target.temp_path)
    return download_size_mismatch_detail(target.expected_size, final_size)


def download_size_mismatch_failure_detail(
    runtime: DownloadOutcomeRuntime,
    target: DownloadSizeMismatchTarget,
    raw_mismatch_detail: Tuple[str, str],
) -> DownloadFailureDetail:
    mismatch_detail = download_failure_detail_from_raw_mismatch(raw_mismatch_detail)
    record_download_size_mismatch_failure(runtime, target, mismatch_detail)
    return mismatch_detail


def download_failure_detail_from_raw_mismatch(
    raw_mismatch_detail: Tuple[str, str],
) -> DownloadFailureDetail:
    return DownloadFailureDetail(*raw_mismatch_detail)


def record_download_size_mismatch_failure(
    runtime: DownloadOutcomeRuntime,
    target: DownloadSizeMismatchTarget,
    mismatch_detail: DownloadFailureDetail,
) -> None:
    runtime.log(f"   ⚠️ {mismatch_detail.error_message}")
    os.remove(target.temp_path)


def handle_download_stop_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadStopTarget,
) -> None:
    record_download_stop_target(runtime, target)


def record_download_stop_target(
    runtime: DownloadOutcomeRuntime,
    target: DownloadStopTarget,
) -> None:
    failure_detail = download_stop_failure_detail()
    log_download_stop(runtime, failure_detail)
    update_download_stop_status(runtime, target, failure_detail)
    cleanup_stopped_download(target)


def download_stop_failure_detail() -> DownloadFailureDetail:
    return DownloadFailureDetail("stopped", "下载过程中被停止")


def log_download_stop(
    runtime: DownloadOutcomeRuntime,
    failure_detail: DownloadFailureDetail,
) -> None:
    runtime.log(f"🛑 {failure_detail.error_message}")


def update_download_stop_status(
    runtime: DownloadOutcomeRuntime,
    target: DownloadStopTarget,
    failure_detail: DownloadFailureDetail,
) -> None:
    runtime.file_db.update_file_download_status(
        target.file_id,
        "failed",
        error_code=failure_detail.error_code,
        error_message=failure_detail.error_message,
    )


def cleanup_stopped_download(target: DownloadStopTarget) -> None:
    remove_partial_download(target.temp_path)
