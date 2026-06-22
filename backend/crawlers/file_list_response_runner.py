"""File-list response decision runner for ZSXQ file metadata requests."""

from __future__ import annotations

from typing import Any, Dict, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.zsxq_file_downloader_helpers import (
    API_FAILURE_NON_RETRY,
    API_FAILURE_PERMISSION_DENIED_1030,
    API_FAILURE_RETRY,
    HTTP_FAILURE_NON_RETRY,
    HTTP_FAILURE_RETRY,
    file_list_api_failure_plan,
    file_list_response_page,
    http_failure_plan,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    ApiJsonParseResult,
    FileListApiFailureResponseTarget,
    FileListHttpFailureResponseTarget,
    FileListOkDataTarget,
    FileListOkResponseTarget,
    FileListResponseDecision,
    FileListResponseStatusTarget,
    FileListResponseTarget,
    FileListSuccessResponseTarget,
)


class FileListResponseRuntime(Protocol):
    def _parse_api_json_response(
        self,
        response: Any,
        attempt: int,
        max_retries: int,
    ) -> ApiJsonParseResult:
        ...


def handle_file_list_success_response(
    runtime: FileListResponseRuntime,
    data: Dict[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    return handle_file_list_success_response_target(FileListSuccessResponseTarget(data, attempt))


def handle_file_list_success_response_target(
    target: FileListSuccessResponseTarget,
) -> Dict[str, Any]:
    files, _ = file_list_response_page(target.data)
    if target.attempt > 0:
        print(f"   ✅ 重试成功！第{target.attempt}次重试获取到文件列表")
    else:
        print(f"   ✅ 获取成功: {len(files)}个文件")
    return target.data


def handle_file_list_api_failure_response(
    runtime: FileListResponseRuntime,
    data: Dict[str, Any],
    attempt: int,
    max_retries: int,
) -> str:
    return handle_file_list_api_failure_response_target(FileListApiFailureResponseTarget(data, attempt, max_retries))


def handle_file_list_api_failure_response_target(
    target: FileListApiFailureResponseTarget,
) -> str:
    api_failure = file_list_api_failure_plan(
        target.data,
        target.attempt,
        target.max_retries,
    )
    for message in api_failure["messages"]:
        print(message)
    return api_failure["failure_class"]


def handle_file_list_http_failure_response(
    runtime: FileListResponseRuntime,
    response: Any,
    attempt: int,
    max_retries: int,
) -> str:
    return handle_file_list_http_failure_response_target(FileListHttpFailureResponseTarget(response, attempt, max_retries))


def handle_file_list_http_failure_response_target(
    target: FileListHttpFailureResponseTarget,
) -> str:
    http_failure = http_failure_plan(
        target.response.status_code,
        target.response.text,
        target.attempt,
        target.max_retries,
    )
    for message in http_failure["messages"]:
        print(message)
    return http_failure["failure_class"]


def file_list_api_failure_decision(failure_class: str) -> FileListResponseDecision:
    if failure_class == API_FAILURE_RETRY:
        return FileListResponseDecision(None, True, False)
    if failure_class in {API_FAILURE_NON_RETRY, API_FAILURE_PERMISSION_DENIED_1030}:
        return FileListResponseDecision(None, False, True)
    return FileListResponseDecision(None, False, False)


def file_list_http_failure_decision(failure_class: str) -> FileListResponseDecision:
    if failure_class == HTTP_FAILURE_RETRY:
        return FileListResponseDecision(None, True, False)
    if failure_class == HTTP_FAILURE_NON_RETRY:
        return FileListResponseDecision(None, False, True)
    return FileListResponseDecision(None, False, False)


def handle_file_list_ok_response(
    runtime: FileListResponseRuntime,
    response: Any,
    attempt: int,
    max_retries: int,
) -> FileListResponseDecision:
    return handle_file_list_ok_response_target(runtime, FileListOkResponseTarget(response, attempt, max_retries))


def handle_file_list_ok_response_target(
    runtime: FileListResponseRuntime,
    target: FileListOkResponseTarget,
) -> FileListResponseDecision:
    json_parse = runtime._parse_api_json_response(
        target.response,
        target.attempt,
        target.max_retries,
    )
    if json_parse.should_retry:
        return FileListResponseDecision(None, True, False)
    return file_list_ok_data_decision_target(
        runtime,
        FileListOkDataTarget(
            json_parse.data,
            target.attempt,
            target.max_retries,
        ),
    )


def file_list_ok_data_decision_target(
    runtime: FileListResponseRuntime,
    target: FileListOkDataTarget,
) -> FileListResponseDecision:
    if not target.data:
        return FileListResponseDecision(None, True, False)

    if target.data.get("succeeded"):
        return FileListResponseDecision(
            handle_file_list_success_response_target(
                FileListSuccessResponseTarget(target.data, target.attempt),
            ),
            False,
            False,
        )

    failure_class = handle_file_list_api_failure_response_target(
        FileListApiFailureResponseTarget(
            target.data,
            target.attempt,
            target.max_retries,
        ),
    )
    return file_list_api_failure_decision(failure_class)


def handle_file_list_response(
    runtime: FileListResponseRuntime,
    response: Any,
    attempt: int,
    max_retries: int,
) -> FileListResponseDecision:
    return handle_file_list_response_target(runtime, FileListResponseTarget(response, attempt, max_retries))


def handle_file_list_response_target(
    runtime: FileListResponseRuntime,
    target: FileListResponseTarget,
) -> FileListResponseDecision:
    print(f"   📊 响应状态: {target.response.status_code}")
    return file_list_response_status_decision_target(
        runtime,
        FileListResponseStatusTarget(
            target.response,
            target.attempt,
            target.max_retries,
        ),
    )


def file_list_response_status_decision_target(
    runtime: FileListResponseRuntime,
    target: FileListResponseStatusTarget,
) -> FileListResponseDecision:
    if target.response.status_code == 200:
        return handle_file_list_ok_response_target(
            runtime,
            FileListOkResponseTarget(
                target.response,
                target.attempt,
                target.max_retries,
            ),
        )

    http_failure_class = handle_file_list_http_failure_response_target(
        FileListHttpFailureResponseTarget(
            target.response,
            target.attempt,
            target.max_retries,
        ),
    )
    return file_list_http_failure_decision(http_failure_class)
