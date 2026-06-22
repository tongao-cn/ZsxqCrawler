from __future__ import annotations

import json
from typing import Any

from backend.core.console_output import safe_console_print as print
from backend.core.log_redaction import redact_json_like
from backend.crawlers.zsxq_file_downloader_helpers import (
    json_decode_failure_plan,
    should_log_full_response,
)
from backend.crawlers.zsxq_file_downloader_targets import (
    ApiJsonParseResult,
    JsonDecodeFailureOutputTarget,
    ParseApiJsonResponseTarget,
)


def json_decode_failure_result_with_output(
    target: JsonDecodeFailureOutputTarget,
) -> ApiJsonParseResult:
    decode_failure = json_decode_failure_plan(
        target.exc,
        target.response_text,
        target.attempt,
        target.max_retries,
    )
    for message in decode_failure["messages"]:
        print(message)
    return ApiJsonParseResult(None, decode_failure["should_retry"])


def parse_api_json_response(
    response: Any,
    attempt: int,
    max_retries: int,
) -> ApiJsonParseResult:
    return parse_api_json_response_target(
        ParseApiJsonResponseTarget(response, attempt, max_retries),
    )


def parse_api_json_response_target(
    target: ParseApiJsonResponseTarget,
) -> ApiJsonParseResult:
    try:
        data = target.response.json()
    except json.JSONDecodeError as exc:
        return json_decode_failure_result_with_output(
            JsonDecodeFailureOutputTarget(
                exc,
                target.response.text,
                target.attempt,
                target.max_retries,
            ),
        )

    if should_log_full_response(target.attempt, target.max_retries, data.get("succeeded")):
        print(f"   📋 响应内容: {json.dumps(redact_json_like(data), ensure_ascii=False, indent=2)}")
    return ApiJsonParseResult(data, False)
