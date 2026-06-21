from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from backend.core.ai_provider_config import (
    DEFAULT_FALLBACK_BASE_URL,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_FALLBACK_WIRE_API,
    get_openai_compatible_config,
)
from backend.services.ai_client import AITextRequest


MISSING_OPENAI_RUNTIME_API_KEY_MESSAGE = "OPENAI_API_KEY not set and config.toml [ai].api_key is empty"


@dataclass(frozen=True)
class AIRuntimeTextSettings:
    api_key: str
    model: str
    api_base: str
    wire_api: str


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
    get_ai_config: Callable[[], Mapping[str, Any]] = get_openai_compatible_config,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    wire_api: Optional[str] = None,
    reasoning_effort: str = "",
    timeout: int = 180,
    responses_text_format: Optional[Dict[str, Any]] = None,
    chat_response_format: Optional[Dict[str, Any]] = None,
) -> AITextRequest:
    settings = resolve_runtime_text_settings(
        get_ai_config=get_ai_config,
        model=model,
        api_base=api_base,
        wire_api=wire_api,
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
