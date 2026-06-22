"""File-list request runner for ZSXQ file metadata requests."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.zsxq_file_downloader_helpers import (
    file_list_request_params,
    file_list_start_messages,
    retry_exhausted_message,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    FetchFileListTarget,
    FileListRequestAttemptTarget,
    FileListRequestContext,
    FileListRequestExceptionTarget,
    FileListRequestTarget,
    FileListResponseDecision,
    FileListResponseTarget,
)


class FileListRequestRuntime(Protocol):
    base_url: str
    group_id: Any
    session: Any

    def log(self, message: str) -> None:
        ...

    def _prepare_retry_api_request(self, attempt: int) -> Dict[str, str]:
        ...


def fetch_file_list_target(
    runtime: FileListRequestRuntime,
    target: FetchFileListTarget,
) -> Optional[Dict[str, Any]]:
    request_context = runtime._start_file_list_request(target)  # type: ignore[attr-defined]
    return runtime._run_file_list_request_loop(request_context)  # type: ignore[attr-defined]


def run_file_list_request_loop(
    runtime: FileListRequestRuntime,
    request_context: FileListRequestContext,
) -> Optional[Dict[str, Any]]:
    for attempt in range(request_context.max_retries):
        decision = runtime._run_file_list_request_attempt(  # type: ignore[attr-defined]
            FileListRequestAttemptTarget(request_context, attempt),
        )
        if decision.result is not None:
            return decision.result
        if decision.should_retry:
            continue
        if decision.should_stop:
            return None

    print(retry_exhausted_message(request_context.max_retries))
    return None


def start_file_list_request(
    runtime: FileListRequestRuntime,
    target: FetchFileListTarget,
) -> FileListRequestContext:
    url = f"{runtime.base_url}/v2/groups/{runtime.group_id}/files"
    params = file_list_request_params(target.count, target.sort, target.index)
    max_retries = 10

    for message in file_list_start_messages(target.count, target.sort, target.index, url):
        runtime.log(message)

    return FileListRequestContext(url, params, max_retries)


def request_file_list_response_target(
    runtime: FileListRequestRuntime,
    target: FileListRequestTarget,
) -> Any:
    return runtime.session.get(
        target.url,
        headers=target.headers,
        params=target.params,
        timeout=30,
    )


def run_file_list_request_attempt(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
) -> FileListResponseDecision:
    headers = runtime._file_list_request_attempt_headers(target)  # type: ignore[attr-defined]

    try:
        return runtime._file_list_request_attempt_decision(target, headers)  # type: ignore[attr-defined]
    except Exception as e:
        return runtime._handle_file_list_request_attempt_exception(target, e)  # type: ignore[attr-defined]


def file_list_request_attempt_headers(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
) -> Dict[str, str]:
    return runtime._prepare_retry_api_request(target.attempt)


def file_list_request_attempt_decision(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
    headers: Dict[str, str],
) -> FileListResponseDecision:
    response = runtime._request_file_list_attempt_response(target, headers)  # type: ignore[attr-defined]
    return runtime._handle_file_list_request_attempt_response(target, response)  # type: ignore[attr-defined]


def request_file_list_attempt_response(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
    headers: Dict[str, str],
) -> Any:
    return runtime._request_file_list_response_target(  # type: ignore[attr-defined]
        runtime._file_list_request_target_for_attempt(target, headers),  # type: ignore[attr-defined]
    )


def file_list_request_target_for_attempt(
    target: FileListRequestAttemptTarget,
    headers: Dict[str, str],
) -> FileListRequestTarget:
    return FileListRequestTarget(
        target.request_context.url,
        headers,
        target.request_context.params,
    )


def handle_file_list_request_attempt_response(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
    response: Any,
) -> FileListResponseDecision:
    return runtime._handle_file_list_response_target(  # type: ignore[attr-defined]
        FileListResponseTarget(
            response,
            target.attempt,
            target.request_context.max_retries,
        ),
    )


def handle_file_list_request_attempt_exception(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
    exc: Exception,
) -> FileListResponseDecision:
    should_retry = runtime._handle_file_list_request_exception_target(  # type: ignore[attr-defined]
        FileListRequestExceptionTarget(
            exc,
            target.attempt,
            target.request_context.max_retries,
        ),
    )
    return runtime._file_list_request_exception_decision(should_retry)  # type: ignore[attr-defined]


def file_list_request_exception_decision(
    should_retry: bool,
) -> FileListResponseDecision:
    return FileListResponseDecision(None, should_retry, False)
