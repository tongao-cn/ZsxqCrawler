"""Retry and failure classification policy for ZSXQ file API calls."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.core.log_redaction import redact_response_text


RETRYABLE_API_ERROR_CODES = {"1059", "500", "502", "503", "504"}
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
API_FAILURE_RETRY = "retry"
API_FAILURE_NON_RETRY = "non_retry"
API_FAILURE_RETRY_EXHAUSTED = "retry_exhausted"
API_FAILURE_PERMISSION_DENIED_1030 = "permission_denied_1030"
HTTP_FAILURE_RETRY = "retry"
HTTP_FAILURE_NON_RETRY = "non_retry"
HTTP_FAILURE_RETRY_EXHAUSTED = "retry_exhausted"


def is_retryable_api_error(error_code: Any) -> bool:
    return str(error_code) in RETRYABLE_API_ERROR_CODES


def is_retryable_http_status(status_code: int) -> bool:
    return int(status_code) in RETRYABLE_HTTP_STATUS_CODES


def has_retry_attempt_remaining(attempt: int, max_retries: int) -> bool:
    return int(attempt) < int(max_retries) - 1


def should_retry_api_error(error_code: Any, attempt: int, max_retries: int) -> bool:
    return is_retryable_api_error(error_code) and has_retry_attempt_remaining(attempt, max_retries)


def should_retry_http_status(status_code: int, attempt: int, max_retries: int) -> bool:
    return is_retryable_http_status(status_code) and has_retry_attempt_remaining(attempt, max_retries)


def should_log_full_response(attempt: int, max_retries: int, succeeded: Any) -> bool:
    return int(attempt) == 0 or int(attempt) == int(max_retries) - 1 or bool(succeeded)


def api_failure_detail(data: Dict[str, Any]) -> tuple[Any, Any]:
    return data.get("message", data.get("error", "未知错误")), data.get("code", "N/A")


def classify_api_failure(error_code: Any, attempt: int, max_retries: int) -> str:
    if str(error_code) == "1030":
        return API_FAILURE_PERMISSION_DENIED_1030
    if not is_retryable_api_error(error_code):
        return API_FAILURE_NON_RETRY
    if has_retry_attempt_remaining(attempt, max_retries):
        return API_FAILURE_RETRY
    return API_FAILURE_RETRY_EXHAUSTED


def file_list_api_failure_plan(data: Dict[str, Any], attempt: int, max_retries: int) -> Dict[str, Any]:
    error_msg, error_code = api_failure_detail(data)
    failure_class = classify_api_failure(error_code, attempt, max_retries)
    messages = [f"   ❌ API返回失败: {error_msg} (代码: {error_code})"]

    if failure_class == API_FAILURE_RETRY:
        messages.append("   🔄 检测到可重试错误，准备重试...")
    elif failure_class in {API_FAILURE_NON_RETRY, API_FAILURE_PERMISSION_DENIED_1030}:
        messages.append("   🚫 非可重试错误，停止重试")

    return {
        "error_msg": error_msg,
        "error_code": error_code,
        "failure_class": failure_class,
        "messages": tuple(messages),
    }


def download_url_api_failure_plan(data: Dict[str, Any], attempt: int, max_retries: int) -> Dict[str, Any]:
    error_msg, error_code = api_failure_detail(data)
    failure_class = classify_api_failure(error_code, attempt, max_retries)
    messages = [f"   ❌ API返回失败: {error_msg} (代码: {error_code})"]
    last_error = None

    if failure_class == API_FAILURE_PERMISSION_DENIED_1030:
        last_error = {
            "code": error_code,
            "message": error_msg,
        }
        messages.append("   🚫 权限不足错误(1030)：此文件可能只能在手机端下载，已跳过当前文件")
    elif failure_class == API_FAILURE_RETRY:
        messages.append("   🔄 检测到可重试错误，准备重试...")
    elif failure_class == API_FAILURE_NON_RETRY:
        messages.append("   🚫 非可重试错误，停止重试")

    return {
        "error_msg": error_msg,
        "error_code": error_code,
        "failure_class": failure_class,
        "messages": tuple(messages),
        "last_download_url_error": last_error,
    }


def classify_http_failure(status_code: int, attempt: int, max_retries: int) -> str:
    if not is_retryable_http_status(status_code):
        return HTTP_FAILURE_NON_RETRY
    if has_retry_attempt_remaining(attempt, max_retries):
        return HTTP_FAILURE_RETRY
    return HTTP_FAILURE_RETRY_EXHAUSTED


def http_failure_plan(
    status_code: int,
    response_text: Any,
    attempt: int,
    max_retries: int,
) -> Dict[str, Any]:
    failure_class = classify_http_failure(status_code, attempt, max_retries)
    messages = [
        f"   ❌ HTTP错误: {status_code}",
        f"   📄 响应内容: {redact_response_text(response_text, limit=200)}",
    ]
    if failure_class == HTTP_FAILURE_RETRY:
        messages.append("   🔄 服务器错误，准备重试...")
    elif failure_class == HTTP_FAILURE_NON_RETRY:
        messages.append("   🚫 非可重试HTTP错误，停止重试")
    return {"failure_class": failure_class, "messages": tuple(messages)}


def request_exception_plan(exc: Exception, attempt: int, max_retries: int) -> Dict[str, Any]:
    should_retry = has_retry_attempt_remaining(attempt, max_retries)
    messages = [f"   ❌ 请求异常: {exc}"]
    if should_retry:
        messages.append("   🔄 请求异常，准备重试...")
    return {"should_retry": should_retry, "messages": tuple(messages)}


def api_retry_wait_message(attempt: int, retry_delay: float) -> str:
    return f"   🔄 第{attempt}次重试，等待{retry_delay:.1f}秒..."


def api_retry_user_agent_message(attempt: int, headers: Dict[str, str]) -> str:
    return f"   🔄 重试#{attempt}: 使用新的User-Agent: {headers.get('User-Agent', 'N/A')[:50]}..."


def retry_exhausted_message(max_retries: int) -> str:
    return f"   🚫 已重试{max_retries}次，全部失败"


def json_decode_failure_plan(exc: Exception, response_text: Any, attempt: int, max_retries: int) -> Dict[str, Any]:
    should_retry = has_retry_attempt_remaining(attempt, max_retries)
    messages = [
        f"   ❌ JSON解析失败: {exc}",
        f"   📄 原始响应: {redact_response_text(response_text, limit=500)}",
    ]
    if should_retry:
        messages.append("   🔄 JSON解析失败，准备重试...")
    return {"should_retry": should_retry, "messages": tuple(messages)}


def download_url_success_plan(attempt: int) -> tuple[str, str]:
    if attempt > 0:
        return f"   ✅ 重试成功！第{attempt}次重试获取到下载链接", "download_url_retry_response"
    return "   ✅ 获取下载链接成功", "download_url_response"


def download_url_from_response_data(data: Dict[str, Any]) -> Optional[str]:
    return data.get("resp_data", {}).get("download_url")


__all__ = [
    "API_FAILURE_NON_RETRY",
    "API_FAILURE_PERMISSION_DENIED_1030",
    "API_FAILURE_RETRY",
    "API_FAILURE_RETRY_EXHAUSTED",
    "HTTP_FAILURE_NON_RETRY",
    "HTTP_FAILURE_RETRY",
    "HTTP_FAILURE_RETRY_EXHAUSTED",
    "RETRYABLE_API_ERROR_CODES",
    "RETRYABLE_HTTP_STATUS_CODES",
    "api_failure_detail",
    "api_retry_user_agent_message",
    "api_retry_wait_message",
    "classify_api_failure",
    "classify_http_failure",
    "download_url_api_failure_plan",
    "download_url_from_response_data",
    "download_url_success_plan",
    "file_list_api_failure_plan",
    "has_retry_attempt_remaining",
    "http_failure_plan",
    "is_retryable_api_error",
    "is_retryable_http_status",
    "json_decode_failure_plan",
    "request_exception_plan",
    "retry_exhausted_message",
    "should_log_full_response",
    "should_retry_api_error",
    "should_retry_http_status",
]
