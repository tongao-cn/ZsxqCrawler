"""AI transport helpers for daily topic reports."""

from __future__ import annotations

import base64
import mimetypes
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.core.image_cache_manager import get_image_cache_manager


def build_image_content_parts(
    group_id: str,
    images: List[Dict[str, Any]],
    *,
    max_image_bytes: int,
) -> List[Dict[str, str]]:
    cache_manager = get_image_cache_manager(group_id)
    content_parts: List[Dict[str, str]] = []
    for image in images:
        url = str(image.get("url") or "").strip()
        if not url:
            continue

        success, cache_path, _error = cache_manager.download_and_cache(url, timeout=15)
        if not success or not cache_path or not cache_path.exists():
            continue
        if cache_path.stat().st_size > max_image_bytes:
            continue

        mime_type = mimetypes.guess_type(str(cache_path))[0] or "image/jpeg"
        encoded = base64.b64encode(cache_path.read_bytes()).decode("ascii")
        content_parts.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
            }
        )
    return content_parts


def extract_response_text(response: Any) -> str:
    text_value = getattr(response, "output_text", None)
    if text_value:
        return str(text_value)

    outputs = getattr(response, "output", []) or []
    chunks = []
    for output in outputs:
        for content in getattr(output, "content", []) or []:
            chunk_text = getattr(content, "text", None)
            if chunk_text:
                chunks.append(str(chunk_text))
    return "\n".join(chunks)


def call_report_ai(
    user_prompt: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
    max_image_bytes: int,
) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = str(runtime_ai_config.get("model") or get_default_model())
    api_base = str(runtime_ai_config.get("base_url") or get_default_base_url())
    wire_api = str(runtime_ai_config.get("wire_api") or get_default_wire_api())
    reasoning_effort = get_summary_reasoning_effort()
    image_inputs = image_inputs or []

    messages = [
        {
            "role": "system",
            "content": (
                "你是知识星球社群日报分析助手。"
                "请只基于输入的话题数据分析，不要编造未出现的信息。"
                "输出中文 Markdown，重点给群主/运营者可执行的信息密度。"
            ),
        },
    ]

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=180)
    if wire_api.strip().lower() == "responses":
        user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
        user_content.extend(build_image_content_parts(group_id, image_inputs, max_image_bytes=max_image_bytes))
        messages.append({"role": "user", "content": user_content})
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
        )
        return extract_response_text(response).strip(), model

    user_content = [{"type": "text", "text": user_prompt}]
    for image_part in build_image_content_parts(group_id, image_inputs, max_image_bytes=max_image_bytes):
        user_content.append({"type": "image_url", "image_url": {"url": image_part["image_url"]}})
    messages.append({"role": "user", "content": user_content if len(user_content) > 1 else user_prompt})
    response = client.chat.completions.create(model=model, messages=messages, stream=False)
    return str(response.choices[0].message.content or "").strip(), model
