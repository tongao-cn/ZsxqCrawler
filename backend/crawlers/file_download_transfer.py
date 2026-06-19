from __future__ import annotations

from typing import Any, Callable, NamedTuple, Optional


class DownloadFailureDetail(NamedTuple):
    error_code: str
    error_message: str


class DownloadFileTarget(NamedTuple):
    file_id: int
    file_name: str
    file_size: int
    safe_filename: str
    file_path: str


class DownloadAttemptResult(NamedTuple):
    success_result: Optional[bool]
    failure_detail: Optional[DownloadFailureDetail]
    file_name: str
    safe_filename: str
    file_path: str


class DownloadRetryState(NamedTuple):
    file_name: str
    safe_filename: str
    file_path: str
    last_error_code: Optional[str]
    last_error: Optional[str]


class DownloadAttemptResultTarget(NamedTuple):
    attempt_result: DownloadAttemptResult
    retry_state: DownloadRetryState


class DownloadRetryExceptionTarget(NamedTuple):
    exc: Exception
    retry_state: DownloadRetryState


class DownloadRetryLoopAttemptTarget(NamedTuple):
    attempt: int
    download_retries: int
    prepared_file: DownloadFileTarget
    retry_state: DownloadRetryState


class DownloadRetryDecision(NamedTuple):
    state: DownloadRetryState
    result: Optional[bool]


class DownloadRetryLoopFailureTarget(NamedTuple):
    prepared_file: DownloadFileTarget
    download_retries: int
    retry_state: DownloadRetryState


RunDownloadAttempt = Callable[[DownloadRetryLoopAttemptTarget], DownloadRetryDecision]
FinishDownloadFailure = Callable[[DownloadRetryLoopFailureTarget], bool]


def initial_download_retry_state(prepared_file: DownloadFileTarget) -> DownloadRetryState:
    return DownloadRetryState(
        prepared_file.file_name,
        prepared_file.safe_filename,
        prepared_file.file_path,
        None,
        None,
    )


def download_retry_attempt_file(target: DownloadRetryLoopAttemptTarget) -> DownloadFileTarget:
    return target.prepared_file._replace(
        file_name=target.retry_state.file_name,
        safe_filename=target.retry_state.safe_filename,
        file_path=target.retry_state.file_path,
    )


def download_retry_state_after_attempt_result(target: DownloadAttemptResultTarget) -> DownloadRetryState:
    attempt_result = target.attempt_result
    retry_state = target.retry_state
    return DownloadRetryState(
        attempt_result.file_name,
        attempt_result.safe_filename,
        attempt_result.file_path,
        retry_state.last_error_code,
        retry_state.last_error,
    )


def download_retry_decision_after_attempt_result(target: DownloadAttemptResultTarget) -> DownloadRetryDecision:
    attempt_result = target.attempt_result
    retry_state = target.retry_state
    if attempt_result.success_result is False:
        return DownloadRetryDecision(retry_state, False)
    if not attempt_result.failure_detail:
        return DownloadRetryDecision(retry_state, True)
    return DownloadRetryDecision(
        retry_state._replace(
            last_error_code=attempt_result.failure_detail.error_code,
            last_error=attempt_result.failure_detail.error_message,
        ),
        None,
    )


def apply_download_attempt_result(target: DownloadAttemptResultTarget) -> DownloadRetryDecision:
    retry_state = download_retry_state_after_attempt_result(target)
    return download_retry_decision_after_attempt_result(
        DownloadAttemptResultTarget(target.attempt_result, retry_state),
    )


def run_download_retry_loop(
    prepared_file: DownloadFileTarget,
    *,
    download_retries: int,
    run_attempt: RunDownloadAttempt,
    finish_failure: FinishDownloadFailure,
) -> bool:
    retry_state = initial_download_retry_state(prepared_file)

    for attempt in range(download_retries):
        retry_decision = run_attempt(
            DownloadRetryLoopAttemptTarget(
                attempt,
                download_retries,
                prepared_file,
                retry_state,
            ),
        )
        retry_state = retry_decision.state
        if retry_decision.result is None:
            continue
        return retry_decision.result

    return finish_failure(
        DownloadRetryLoopFailureTarget(prepared_file, download_retries, retry_state),
    )
