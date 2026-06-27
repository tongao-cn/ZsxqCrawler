"""OpenAI-compatible AI transport helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass(frozen=True)
class AITextRequest:
    api_key: str
    model: str
    api_base: Optional[str]
    messages: List[Dict[str, Any]]
    wire_api: str = "responses"
    reasoning_effort: str = ""
    responses_text_format: Optional[Dict[str, Any]] = None
    chat_response_format: Optional[Dict[str, Any]] = None


def extract_response_text(response: Any) -> str:
    text_value = getattr(response, "output_text", None)
    if text_value:
        return str(text_value)

    try:
        outputs = getattr(response, "output", []) or []
        chunks: List[str] = []
        for output in outputs:
            for content in getattr(output, "content", []) or []:
                chunk_text = getattr(content, "text", None)
                if chunk_text:
                    chunks.append(str(chunk_text))
        if chunks:
            return "\n".join(chunks)
    except Exception:
        pass

    return ""


def responses_json_schema_text_format(name: str, schema: Dict[str, Any], *, strict: bool = True) -> Dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "strict": strict,
            "schema": schema,
        },
    }


def chat_json_schema_response_format(name: str, schema: Dict[str, Any], *, strict: bool = True) -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": strict,
            "schema": schema,
        },
    }


def call_ai_text(request: AITextRequest) -> str:
    api_key = str(request.api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    client = OpenAI(api_key=api_key, base_url=request.api_base)
    normalized_wire_api = str(request.wire_api or "responses").strip().lower()

    if normalized_wire_api == "responses":
        kwargs: Dict[str, Any] = {
            "model": request.model,
            "input": request.messages,
        }
        reasoning_effort = str(request.reasoning_effort or "").strip()
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        if request.responses_text_format is not None:
            kwargs["text"] = request.responses_text_format
        response = client.responses.create(**kwargs)
        return extract_response_text(response)

    kwargs = {
        "model": request.model,
        "messages": request.messages,
        "stream": False,
    }
    if request.chat_response_format is not None:
        kwargs["response_format"] = request.chat_response_format
    response = client.chat.completions.create(**kwargs)
    return str(response.choices[0].message.content or "")


def is_retryable_ai_error(exc: Exception) -> bool:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError
    except Exception:
        return False

    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)):
        return True

    if isinstance(exc, APIStatusError):
        status_code = int(getattr(exc, "status_code", 0) or 0)
        return status_code == 408 or status_code == 409 or status_code == 429 or status_code >= 500

    return False
