from __future__ import annotations

from typing import Any, Callable, Dict, NamedTuple, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.api_json_response_runner import parse_api_json_response
from backend.crawlers.file_api_retry_policy import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    ApiJsonParseResult,
    DownloadUrlApiFailureResponseTarget,
    DownloadUrlDataDecisionTarget,
    DownloadUrlHttpFailureResponseTarget,
    DownloadUrlOkResponseTarget,
    DownloadUrlRequestExceptionTarget,
    DownloadUrlRequestTarget,
    DownloadUrlResponseTarget,
    DownloadUrlSuccessResponseTarget,
)


DOWNLOAD_URL_REQUEST_TIMEOUT_SECONDS = 30


class DownloadUrlResponseDecision(NamedTuple):
    download_url: Optional[str]
    should_retry: bool
    should_stop: bool


class DownloadUrlAttemptTarget(NamedTuple):
    url: str
    file_id: int
    attempt: int
    max_retries: int


class DownloadUrlRetryLoopTarget(NamedTuple):
    url: str
    file_id: int
    max_retries: int


class DownloadUrlRetryLoopStepDecision(NamedTuple):
    result: Optional[str]
    should_continue: bool


class DownloadUrlResponseRuntime(Protocol):
    def _handle_download_url_success_response_target(
        self,
        target: DownloadUrlSuccessResponseTarget,
    ) -> Optional[str]:
        ...

    def _handle_download_url_api_failure_response_target(
        self,
        target: DownloadUrlApiFailureResponseTarget,
    ) -> str:
        ...

    def _handle_download_url_http_failure_response_target(
        self,
        target: DownloadUrlHttpFailureResponseTarget,
    ) -> str:
        ...


class DownloadUrlAttemptRuntime(DownloadUrlResponseRuntime, Protocol):
    session: Any

    def _prepare_retry_api_request(
        self,
        attempt: int,
        file_id: Optional[int] = None,
    ) -> Dict[str, str]:
        ...

    def _handle_download_url_request_exception_target(
        self,
        target: DownloadUrlRequestExceptionTarget,
    ) -> bool:
        ...


RunDownloadUrlAttempt = Callable[[DownloadUrlAttemptTarget], DownloadUrlResponseDecision]
FinishDownloadUrlRetryExhausted = Callable[[DownloadUrlRetryLoopTarget], None]


def request_download_url_response_target(
    runtime: DownloadUrlAttemptRuntime,
    target: DownloadUrlRequestTarget,
    *,
    timeout_seconds: int = DOWNLOAD_URL_REQUEST_TIMEOUT_SECONDS,
) -> Any:
    return runtime.session.get(
        target.url,
        headers=target.headers,
        timeout=timeout_seconds,
    )


def download_url_http_failure_decision(
    failure_class: str,
) -> DownloadUrlResponseDecision:
    if failure_class == HTTP_FAILURE_RETRY:
        return DownloadUrlResponseDecision(None, True, False)
    if failure_class == HTTP_FAILURE_NON_RETRY:
        return DownloadUrlResponseDecision(None, False, True)
    return DownloadUrlResponseDecision(None, False, False)


def download_url_api_failure_decision(
    failure_class: str,
) -> DownloadUrlResponseDecision:
    if failure_class == API_FAILURE_PERMISSION_DENIED_1030:
        return DownloadUrlResponseDecision(None, False, True)
    if failure_class == API_FAILURE_RETRY:
        return DownloadUrlResponseDecision(None, True, False)
    if failure_class == API_FAILURE_NON_RETRY:
        return DownloadUrlResponseDecision(None, False, True)
    return DownloadUrlResponseDecision(None, False, False)


def handle_download_url_ok_response_target(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlOkResponseTarget,
) -> DownloadUrlResponseDecision:
    json_parse = parse_api_json_response(
        target.response,
        target.attempt,
        target.max_retries,
    )
    return download_url_json_parse_decision(runtime, target, json_parse)


def download_url_json_parse_decision(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlOkResponseTarget,
    json_parse: ApiJsonParseResult,
) -> DownloadUrlResponseDecision:
    if json_parse.should_retry:
        return DownloadUrlResponseDecision(None, True, False)
    data = json_parse.data
    if not data:
        return DownloadUrlResponseDecision(None, True, False)

    return download_url_data_decision_target(
        runtime,
        DownloadUrlDataDecisionTarget(
            data,
            target.file_id,
            target.attempt,
            target.max_retries,
            target.headers,
            target.response.status_code,
        ),
    )


def download_url_data_decision_target(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlDataDecisionTarget,
) -> DownloadUrlResponseDecision:
    if target.data.get('succeeded'):
        return download_url_success_data_decision(runtime, target)

    return download_url_api_failure_data_decision(runtime, target)


def download_url_success_data_decision(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlDataDecisionTarget,
) -> DownloadUrlResponseDecision:
    download_url = runtime._handle_download_url_success_response_target(
        DownloadUrlSuccessResponseTarget(
            target.data,
            target.file_id,
            target.attempt,
            target.headers,
            target.http_status,
        ),
    )
    return DownloadUrlResponseDecision(download_url, False, False)


def download_url_api_failure_data_decision(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlDataDecisionTarget,
) -> DownloadUrlResponseDecision:
    failure_class = runtime._handle_download_url_api_failure_response_target(
        DownloadUrlApiFailureResponseTarget(
            target.data,
            target.file_id,
            target.attempt,
            target.max_retries,
            target.headers,
            target.http_status,
        ),
    )

    return download_url_api_failure_decision(failure_class)


def download_url_status_decision(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlResponseTarget,
) -> DownloadUrlResponseDecision:
    if target.response.status_code == 200:
        return handle_download_url_ok_response_target(
            runtime,
            DownloadUrlOkResponseTarget(
                target.response,
                target.file_id,
                target.attempt,
                target.max_retries,
                target.headers,
            ),
        )

    http_failure_class = runtime._handle_download_url_http_failure_response_target(
        DownloadUrlHttpFailureResponseTarget(
            target.response.status_code,
            target.response.text,
            target.attempt,
            target.max_retries,
        ),
    )
    return download_url_http_failure_decision(http_failure_class)


def handle_download_url_response_target(
    runtime: DownloadUrlResponseRuntime,
    target: DownloadUrlResponseTarget,
) -> DownloadUrlResponseDecision:
    print(f"   📊 响应状态: {target.response.status_code}")
    return download_url_status_decision(runtime, target)


def handle_download_url_attempt_response(
    runtime: DownloadUrlAttemptRuntime,
    target: DownloadUrlAttemptTarget,
    headers: Dict[str, str],
    response: Any,
) -> DownloadUrlResponseDecision:
    return handle_download_url_response_target(
        runtime,
        DownloadUrlResponseTarget(
            response,
            target.file_id,
            target.attempt,
            target.max_retries,
            headers,
        ),
    )


def handle_download_url_attempt_exception(
    runtime: DownloadUrlAttemptRuntime,
    target: DownloadUrlAttemptTarget,
    exc: Exception,
) -> DownloadUrlResponseDecision:
    if runtime._handle_download_url_request_exception_target(
        DownloadUrlRequestExceptionTarget(exc, target.attempt, target.max_retries),
    ):
        return DownloadUrlResponseDecision(None, True, False)
    return DownloadUrlResponseDecision(None, False, False)


def run_download_url_attempt(
    runtime: DownloadUrlAttemptRuntime,
    target: DownloadUrlAttemptTarget,
    *,
    timeout_seconds: int = DOWNLOAD_URL_REQUEST_TIMEOUT_SECONDS,
) -> DownloadUrlResponseDecision:
    headers = runtime._prepare_retry_api_request(target.attempt, file_id=target.file_id)

    try:
        response = request_download_url_response_target(
            runtime,
            DownloadUrlRequestTarget(target.url, headers),
            timeout_seconds=timeout_seconds,
        )
        return handle_download_url_attempt_response(runtime, target, headers, response)
    except Exception as exc:
        return handle_download_url_attempt_exception(runtime, target, exc)


def download_url_retry_loop_step_decision(
    decision: DownloadUrlResponseDecision,
) -> DownloadUrlRetryLoopStepDecision:
    if decision.download_url:
        return DownloadUrlRetryLoopStepDecision(decision.download_url, False)
    if decision.should_retry:
        return DownloadUrlRetryLoopStepDecision(None, True)
    if decision.should_stop:
        return DownloadUrlRetryLoopStepDecision(None, False)
    return DownloadUrlRetryLoopStepDecision(None, True)


def run_download_url_retry_loop(
    target: DownloadUrlRetryLoopTarget,
    *,
    run_attempt: RunDownloadUrlAttempt,
    finish_exhausted: FinishDownloadUrlRetryExhausted,
) -> Optional[str]:
    for attempt in range(target.max_retries):
        decision = run_attempt(
            DownloadUrlAttemptTarget(target.url, target.file_id, attempt, target.max_retries),
        )
        step_decision = download_url_retry_loop_step_decision(decision)
        if step_decision.should_continue:
            continue
        return step_decision.result

    finish_exhausted(target)
    return None
