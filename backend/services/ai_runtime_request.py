from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from backend.core.ai_provider_config import (
    DEFAULT_FALLBACK_BASE_URL,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_FALLBACK_WIRE_API,
    get_openai_compatible_config,
)
from backend.services.ai_client import (
    AITextRequest,
    call_ai_text,
    chat_json_schema_response_format,
    responses_json_schema_text_format,
)
from backend.services.ai_json_utils import JsonObjectParseError, require_json_object


MISSING_OPENAI_RUNTIME_API_KEY_MESSAGE = "OPENAI_API_KEY not set and config.toml [ai].api_key is empty"


@dataclass(frozen=True)
class AIRuntimeTextSettings:
    api_key: str
    model: str
    api_base: str
    wire_api: str


@dataclass(frozen=True)
class AIRuntimeTextResult:
    text: str
    model: str


@dataclass(frozen=True)
class AIRuntimeStructuredObjectResult:
    payload: Dict[str, Any]
    text: str
    model: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def resolve_runtime_text_settings(
    *,
    get_ai_config: Callable[[], Mapping[str, Any]] = get_openai_compatible_config,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    wire_api: Optional[str] = None,
) -> AIRuntimeTextSettings:
    runtime_ai_config = get_ai_config()
    api_key = _text(runtime_ai_config.get("api_key"))
    if not api_key:
        raise RuntimeError(MISSING_OPENAI_RUNTIME_API_KEY_MESSAGE)

    return AIRuntimeTextSettings(
        api_key=api_key,
        model=_text(model) or _text(runtime_ai_config.get("model")) or DEFAULT_FALLBACK_MODEL,
        api_base=(
            _text(api_base)
            or _text(runtime_ai_config.get("base_url"))
            or _text(runtime_ai_config.get("api_base"))
            or DEFAULT_FALLBACK_BASE_URL
        ),
        wire_api=_text(wire_api) or _text(runtime_ai_config.get("wire_api")) or DEFAULT_FALLBACK_WIRE_API,
    )


def build_runtime_ai_text_request(
    messages: List[Dict[str, Any]],
    *,
    settings: Optional[AIRuntimeTextSettings] = None,
    get_ai_config: Callable[[], Mapping[str, Any]] = get_openai_compatible_config,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    wire_api: Optional[str] = None,
    reasoning_effort: str = "",
    timeout: int = 180,
    responses_text_format: Optional[Dict[str, Any]] = None,
    chat_response_format: Optional[Dict[str, Any]] = None,
) -> AITextRequest:
    if settings is None:
        settings = resolve_runtime_text_settings(
            get_ai_config=get_ai_config,
            model=model,
            api_base=api_base,
            wire_api=wire_api,
        )
    else:
        settings = AIRuntimeTextSettings(
            api_key=settings.api_key,
            model=_text(model) or settings.model,
            api_base=_text(api_base) or settings.api_base,
            wire_api=_text(wire_api) or settings.wire_api,
        )
    return AITextRequest(
        api_key=settings.api_key,
        model=settings.model,
        api_base=settings.api_base,
        messages=messages,
        wire_api=settings.wire_api,
        reasoning_effort=_text(reasoning_effort),
        timeout=timeout,
        responses_text_format=responses_text_format,
        chat_response_format=chat_response_format,
    )


def call_runtime_ai_text(
    messages: List[Dict[str, Any]],
    *,
    settings: Optional[AIRuntimeTextSettings] = None,
    get_ai_config: Callable[[], Mapping[str, Any]] = get_openai_compatible_config,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    wire_api: Optional[str] = None,
    reasoning_effort: str = "",
    timeout: int = 180,
    responses_text_format: Optional[Dict[str, Any]] = None,
    chat_response_format: Optional[Dict[str, Any]] = None,
    call_text: Callable[[AITextRequest], str] = call_ai_text,
) -> AIRuntimeTextResult:
    request = build_runtime_ai_text_request(
        messages,
        settings=settings,
        get_ai_config=get_ai_config,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        responses_text_format=responses_text_format,
        chat_response_format=chat_response_format,
    )
    return AIRuntimeTextResult(text=call_text(request), model=request.model)


def call_structured_ai_object(
    messages: List[Dict[str, Any]],
    *,
    schema_name: str,
    schema: Dict[str, Any],
    label: str,
    settings: Optional[AIRuntimeTextSettings] = None,
    get_ai_config: Callable[[], Mapping[str, Any]] = get_openai_compatible_config,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    wire_api: Optional[str] = None,
    reasoning_effort: str = "",
    timeout: int = 180,
    call_text: Callable[[AITextRequest], str] = call_ai_text,
) -> AIRuntimeStructuredObjectResult:
    result = call_runtime_ai_text(
        messages,
        settings=settings,
        get_ai_config=get_ai_config,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        responses_text_format=responses_json_schema_text_format(schema_name, schema),
        chat_response_format=chat_json_schema_response_format(schema_name, schema),
        call_text=call_text,
    )
    try:
        payload = require_json_object(result.text, label=label)
    except JsonObjectParseError as exc:
        raise RuntimeError(f"{label}不是合法 JSON: {result.text[:200]}") from exc
    return AIRuntimeStructuredObjectResult(payload=payload, text=result.text, model=result.model)
