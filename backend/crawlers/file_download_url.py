from __future__ import annotations

from typing import Any, Callable, Dict, NamedTuple, Optional, Protocol

from backend.crawlers.zsxq_file_downloader_targets import (
    DownloadUrlRequestExceptionTarget,
    DownloadUrlRequestTarget,
    DownloadUrlResponseTarget,
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


class DownloadUrlAttemptRuntime(Protocol):
    session: Any

    def _prepare_retry_api_request(
        self,
        attempt: int,
        file_id: Optional[int] = None,
    ) -> Dict[str, str]:
        ...

    def _handle_download_url_response_target(
        self,
        target: DownloadUrlResponseTarget,
    ) -> DownloadUrlResponseDecision:
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


def handle_download_url_attempt_response(
    runtime: DownloadUrlAttemptRuntime,
    target: DownloadUrlAttemptTarget,
    headers: Dict[str, str],
    response: Any,
) -> DownloadUrlResponseDecision:
    return runtime._handle_download_url_response_target(
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
