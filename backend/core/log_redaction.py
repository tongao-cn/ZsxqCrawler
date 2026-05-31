from __future__ import annotations

import json
import re
from typing import Any, Mapping


REDACTED = "<redacted>"

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "download-url",
    "download_url",
    "signature",
    "token",
)
_SENSITIVE_HEADER_KEYS = {
    "x-aduid",
    "x-request-id",
}


def _normalized_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def is_sensitive_log_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    if normalized in _SENSITIVE_HEADER_KEYS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_json_like(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_log_key(key) else redact_json_like(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json_like(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_json_like(item) for item in value)
    return value


def redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return dict(redact_json_like(mapping))


def redact_text(text: Any, *, limit: int | None = None) -> str:
    redacted = str(text or "")
    redacted = re.sub(
        r"(?i)((?:cookie|authorization|x-signature|x-aduid|x-request-id)\s*[:=]\s*)([^\r\n;,}]+)",
        rf"\1{REDACTED}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)([\"']?(?:download_url|access_token|token)[\"']?\s*[:=]\s*[\"'])([^\"'\r\n]+)([\"'])",
        rf"\1{REDACTED}\3",
        redacted,
    )
    if limit is not None and len(redacted) > limit:
        return redacted[:limit] + "..."
    return redacted


def redact_response_text(text: Any, *, limit: int | None = None) -> str:
    raw_text = str(text or "")
    try:
        parsed = json.loads(raw_text)
    except Exception:
        return redact_text(raw_text, limit=limit)

    redacted = json.dumps(redact_json_like(parsed), ensure_ascii=False)
    if limit is not None and len(redacted) > limit:
        return redacted[:limit] + "..."
    return redacted
