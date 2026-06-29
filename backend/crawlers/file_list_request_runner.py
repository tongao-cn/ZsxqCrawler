"""File-list request runner for ZSXQ file metadata requests."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.file_api_retry_policy import (
    request_exception_plan,
    retry_exhausted_message,
)
from backend.crawlers.zsxq_file_downloader_helpers import (
    file_list_request_params,
    file_list_start_messages,
)
from backend.crawlers.file_list_response_runner import handle_file_list_response_target
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
    request_context = start_file_list_request(runtime, target)
    return run_file_list_request_loop(runtime, request_context)


def run_file_list_request_loop(
    runtime: FileListRequestRuntime,
    request_context: FileListRequestContext,
) -> Optional[Dict[str, Any]]:
    for attempt in range(request_context.max_retries):
        decision = run_file_list_request_attempt(
            runtime,
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
    headers = file_list_request_attempt_headers(runtime, target)

    try:
        return file_list_request_attempt_decision(runtime, target, headers)
    except Exception as e:
        return handle_file_list_request_attempt_exception(runtime, target, e)


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
    response = request_file_list_attempt_response(runtime, target, headers)
    return handle_file_list_request_attempt_response(runtime, target, response)


def request_file_list_attempt_response(
    runtime: FileListRequestRuntime,
    target: FileListRequestAttemptTarget,
    headers: Dict[str, str],
) -> Any:
    return request_file_list_response_target(
        runtime,
        file_list_request_target_for_attempt(target, headers),
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
    return handle_file_list_response_target(
        runtime,
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
    should_retry = handle_file_list_request_exception_target(
        FileListRequestExceptionTarget(
            exc,
            target.attempt,
            target.request_context.max_retries,
        ),
    )
    return file_list_request_exception_decision(should_retry)


def handle_file_list_request_exception_target(
    target: FileListRequestExceptionTarget,
) -> bool:
    request_exception = request_exception_plan(
        target.exc,
        target.attempt,
        target.max_retries,
    )
    for message in request_exception["messages"]:
        print(message)
    return request_exception["should_retry"]


def file_list_request_exception_decision(
    should_retry: bool,
) -> FileListResponseDecision:
    return FileListResponseDecision(None, should_retry, False)
