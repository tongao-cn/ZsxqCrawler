from __future__ import annotations

from typing import Any, Callable, Dict, NamedTuple, Optional

from backend.crawlers.zsxq_file_downloader_helpers import (
    download_expected_size,
    download_total_size,
    partial_download_path,
)


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


class DownloadExceptionTarget(NamedTuple):
    exc: Exception
    file_path: str


class DownloadResponseTarget(NamedTuple):
    response: Any
    file_target: DownloadFileTarget


class DownloadResponseExceptionTarget(NamedTuple):
    exc: Exception
    file_target: DownloadFileTarget


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


class DownloadRetryExceptionResultTarget(NamedTuple):
    failure_detail: DownloadFailureDetail
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


class DownloadAttemptTarget(NamedTuple):
    attempt: int
    download_retries: int
    file_target: DownloadFileTarget


class DownloadCompletionTarget(NamedTuple):
    file_id: int
    safe_filename: str
    file_path: str
    temp_path: str


class DownloadBodyPreparationTarget(NamedTuple):
    response_headers: Dict[str, Any]
    file_size: int
    file_path: str


class DownloadBodyTarget(NamedTuple):
    total_size: int
    expected_size: int
    temp_path: str


class DownloadBodyWriteTarget(NamedTuple):
    temp_path: str
    total_size: int
    file_id: int


class DownloadBodyResponseTarget(NamedTuple):
    response: Any
    body_target: DownloadBodyWriteTarget


class DownloadBodyFinalizationTarget(NamedTuple):
    expected_size: int
    temp_path: str
    file_id: int
    safe_filename: str
    file_path: str


class DownloadBodyFinalizationDecisionTarget(NamedTuple):
    downloaded_size: Optional[int]
    finalization_target: DownloadBodyFinalizationTarget


class DownloadSizeMismatchTarget(NamedTuple):
    expected_size: int
    temp_path: str


class DownloadHttpFailureTarget(NamedTuple):
    status_code: int


class DownloadBodyResult(NamedTuple):
    success_result: Optional[bool]
    failure_detail: Optional[DownloadFailureDetail]


class DownloadBodyAttemptResultTarget(NamedTuple):
    body_result: DownloadBodyResult
    file_target: DownloadFileTarget


RunDownloadAttempt = Callable[[DownloadRetryLoopAttemptTarget], DownloadRetryDecision]
RunDownloadFileAttempt = Callable[[DownloadAttemptTarget], DownloadAttemptResult]
FinishDownloadFailure = Callable[[DownloadRetryLoopFailureTarget], bool]
RecordDownloadException = Callable[[DownloadExceptionTarget], DownloadFailureDetail]
FindDownloadSizeMismatch = Callable[[DownloadSizeMismatchTarget], Optional[DownloadFailureDetail]]
CompleteSuccessfulDownload = Callable[[DownloadCompletionTarget], None]
WriteDownloadResponseBody = Callable[[DownloadBodyResponseTarget], Optional[int]]
RecordDownloadHttpFailure = Callable[[DownloadHttpFailureTarget], DownloadFailureDetail]
RemovePartialDownload = Callable[[str], bool]
ResolveDownloadResponseTarget = Callable[[DownloadResponseTarget], DownloadFileTarget]


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


def download_retry_state_after_exception_result(target: DownloadRetryExceptionResultTarget) -> DownloadRetryState:
    return target.retry_state._replace(
        last_error_code=target.failure_detail.error_code,
        last_error=target.failure_detail.error_message,
    )


def download_retry_exception_state(
    target: DownloadRetryExceptionTarget,
    *,
    record_exception: RecordDownloadException,
) -> DownloadRetryState:
    retry_state = target.retry_state
    failure_detail = record_exception(
        DownloadExceptionTarget(
            target.exc,
            retry_state.file_path,
        ),
    )
    return download_retry_state_after_exception_result(
        DownloadRetryExceptionResultTarget(failure_detail, retry_state),
    )


def apply_download_retry_exception(
    target: DownloadRetryExceptionTarget,
    *,
    record_exception: RecordDownloadException,
) -> DownloadRetryDecision:
    return DownloadRetryDecision(
        download_retry_exception_state(
            target,
            record_exception=record_exception,
        ),
        None,
    )


def run_download_retry_loop_attempt(
    target: DownloadRetryLoopAttemptTarget,
    *,
    run_download_attempt: RunDownloadFileAttempt,
    record_exception: RecordDownloadException,
) -> DownloadRetryDecision:
    try:
        attempt_result = run_download_attempt(
            DownloadAttemptTarget(
                target.attempt,
                target.download_retries,
                download_retry_attempt_file(target),
            ),
        )
        return apply_download_attempt_result(
            DownloadAttemptResultTarget(attempt_result, target.retry_state),
        )
    except Exception as exc:
        return apply_download_retry_exception(
            DownloadRetryExceptionTarget(exc, target.retry_state),
            record_exception=record_exception,
        )


def download_response_exception_attempt_result(
    target: DownloadResponseExceptionTarget,
    *,
    record_exception: RecordDownloadException,
) -> DownloadAttemptResult:
    file_target = target.file_target
    failure_detail = record_exception(
        DownloadExceptionTarget(
            target.exc,
            file_target.file_path,
        ),
    )
    return DownloadAttemptResult(
        None,
        failure_detail,
        file_target.file_name,
        file_target.safe_filename,
        file_target.file_path,
    )


def stopped_download_body_result() -> DownloadBodyResult:
    return DownloadBodyResult(False, None)


def download_size_mismatch_result(mismatch_detail: DownloadFailureDetail) -> DownloadBodyResult:
    return DownloadBodyResult(None, mismatch_detail)


def successful_download_body_result() -> DownloadBodyResult:
    return DownloadBodyResult(True, None)


def download_body_target_for_preparation(target: DownloadBodyPreparationTarget) -> DownloadBodyTarget:
    total_size = download_total_size(target.response_headers)
    expected_size = download_expected_size(target.file_size, total_size)
    temp_path = partial_download_path(target.file_path)
    return DownloadBodyTarget(total_size, expected_size, temp_path)


def prepare_download_body_target(
    target: DownloadBodyPreparationTarget,
    *,
    remove_partial_download: RemovePartialDownload,
) -> DownloadBodyTarget:
    body_target = download_body_target_for_preparation(target)
    remove_partial_download(body_target.temp_path)
    return body_target


def download_body_preparation_target_for_response(
    target: DownloadResponseTarget,
) -> DownloadBodyPreparationTarget:
    file_target = target.file_target
    return DownloadBodyPreparationTarget(
        target.response.headers,
        file_target.file_size,
        file_target.file_path,
    )


def download_body_write_response_target(
    target: DownloadResponseTarget,
    body_target: DownloadBodyTarget,
) -> DownloadBodyResponseTarget:
    file_target = target.file_target
    return DownloadBodyResponseTarget(
        target.response,
        DownloadBodyWriteTarget(
            body_target.temp_path,
            body_target.total_size,
            file_target.file_id,
        ),
    )


def download_body_finalization_decision_target(
    downloaded_size: Optional[int],
    target: DownloadResponseTarget,
    body_target: DownloadBodyTarget,
) -> DownloadBodyFinalizationDecisionTarget:
    file_target = target.file_target
    return DownloadBodyFinalizationDecisionTarget(
        downloaded_size,
        DownloadBodyFinalizationTarget(
            body_target.expected_size,
            body_target.temp_path,
            file_target.file_id,
            file_target.safe_filename,
            file_target.file_path,
        ),
    )


def download_body_result_for_response(
    target: DownloadResponseTarget,
    body_target: DownloadBodyTarget,
    *,
    write_response_body: WriteDownloadResponseBody,
    find_mismatch_detail: FindDownloadSizeMismatch,
    complete_successful_download: CompleteSuccessfulDownload,
) -> DownloadBodyResult:
    downloaded_size = write_response_body(
        download_body_write_response_target(target, body_target),
    )
    return finalize_download_body_result_decision(
        download_body_finalization_decision_target(
            downloaded_size,
            target,
            body_target,
        ),
        find_mismatch_detail=find_mismatch_detail,
        complete_successful_download=complete_successful_download,
    )


def download_body_result_for_successful_response(
    target: DownloadResponseTarget,
    *,
    remove_partial_download: RemovePartialDownload,
    write_response_body: WriteDownloadResponseBody,
    find_mismatch_detail: FindDownloadSizeMismatch,
    complete_successful_download: CompleteSuccessfulDownload,
) -> DownloadBodyResult:
    body_target = prepare_download_body_target(
        download_body_preparation_target_for_response(target),
        remove_partial_download=remove_partial_download,
    )
    return download_body_result_for_response(
        target,
        body_target,
        write_response_body=write_response_body,
        find_mismatch_detail=find_mismatch_detail,
        complete_successful_download=complete_successful_download,
    )


def download_attempt_result_from_body_result(
    target: DownloadBodyAttemptResultTarget,
) -> DownloadAttemptResult:
    file_target = target.file_target
    body_result = target.body_result
    return DownloadAttemptResult(
        body_result.success_result,
        body_result.failure_detail,
        file_target.file_name,
        file_target.safe_filename,
        file_target.file_path,
    )


def download_attempt_missing_url_result(file_target: DownloadFileTarget) -> DownloadAttemptResult:
    return DownloadAttemptResult(
        False,
        None,
        file_target.file_name,
        file_target.safe_filename,
        file_target.file_path,
    )


def download_attempt_result_for_response_status(
    target: DownloadResponseTarget,
    *,
    remove_partial_download: RemovePartialDownload,
    write_response_body: WriteDownloadResponseBody,
    find_mismatch_detail: FindDownloadSizeMismatch,
    complete_successful_download: CompleteSuccessfulDownload,
    record_http_failure: RecordDownloadHttpFailure,
) -> DownloadAttemptResult:
    if target.response.status_code == 200:
        body_result = download_body_result_for_successful_response(
            target,
            remove_partial_download=remove_partial_download,
            write_response_body=write_response_body,
            find_mismatch_detail=find_mismatch_detail,
            complete_successful_download=complete_successful_download,
        )
        return download_attempt_result_from_body_result(
            DownloadBodyAttemptResultTarget(body_result, target.file_target),
        )

    file_target = target.file_target
    failure_detail = record_http_failure(
        DownloadHttpFailureTarget(target.response.status_code),
    )
    return DownloadAttemptResult(
        None,
        failure_detail,
        file_target.file_name,
        file_target.safe_filename,
        file_target.file_path,
    )


def download_attempt_result_for_response(
    target: DownloadResponseTarget,
    *,
    resolve_response_target: ResolveDownloadResponseTarget,
    remove_partial_download: RemovePartialDownload,
    write_response_body: WriteDownloadResponseBody,
    find_mismatch_detail: FindDownloadSizeMismatch,
    complete_successful_download: CompleteSuccessfulDownload,
    record_http_failure: RecordDownloadHttpFailure,
    record_exception: RecordDownloadException,
) -> DownloadAttemptResult:
    response_download_target = target.file_target
    try:
        response_download_target = resolve_response_target(target)
        return download_attempt_result_for_response_status(
            DownloadResponseTarget(target.response, response_download_target),
            remove_partial_download=remove_partial_download,
            write_response_body=write_response_body,
            find_mismatch_detail=find_mismatch_detail,
            complete_successful_download=complete_successful_download,
            record_http_failure=record_http_failure,
        )
    except Exception as exc:
        return download_response_exception_attempt_result(
            DownloadResponseExceptionTarget(exc, response_download_target),
            record_exception=record_exception,
        )


def download_size_mismatch_target_for_finalization(
    finalization_target: DownloadBodyFinalizationTarget,
) -> DownloadSizeMismatchTarget:
    return DownloadSizeMismatchTarget(
        finalization_target.expected_size,
        finalization_target.temp_path,
    )


def download_completion_target_for_finalization(
    finalization_target: DownloadBodyFinalizationTarget,
) -> DownloadCompletionTarget:
    return DownloadCompletionTarget(
        finalization_target.file_id,
        finalization_target.safe_filename,
        finalization_target.file_path,
        finalization_target.temp_path,
    )


def successful_download_body_result_for_finalization(
    finalization_target: DownloadBodyFinalizationTarget,
    *,
    complete_successful_download: CompleteSuccessfulDownload,
) -> DownloadBodyResult:
    complete_successful_download(
        download_completion_target_for_finalization(finalization_target),
    )
    return successful_download_body_result()


def finalize_download_body_result_decision(
    target: DownloadBodyFinalizationDecisionTarget,
    *,
    find_mismatch_detail: FindDownloadSizeMismatch,
    complete_successful_download: CompleteSuccessfulDownload,
) -> DownloadBodyResult:
    finalization_target = target.finalization_target
    if target.downloaded_size is None:
        return stopped_download_body_result()

    mismatch_detail = find_mismatch_detail(
        download_size_mismatch_target_for_finalization(finalization_target),
    )
    if mismatch_detail:
        return download_size_mismatch_result(mismatch_detail)

    return successful_download_body_result_for_finalization(
        finalization_target,
        complete_successful_download=complete_successful_download,
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
