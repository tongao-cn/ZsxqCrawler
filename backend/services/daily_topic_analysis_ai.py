"""AI transport helpers for daily topic reports."""

from __future__ import annotations

import base64
import mimetypes
from typing import Any, Dict, List, Optional, Tuple

from backend.core.ai_provider_config import (
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.core.image_cache_manager import get_image_cache_manager
from backend.services.ai_client import call_ai_text, extract_response_text as extract_response_text
from backend.services.ai_runtime_request import build_runtime_ai_text_request, resolve_runtime_text_settings


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


def call_report_ai(
    user_prompt: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
    max_image_bytes: int,
) -> Tuple[str, str]:
    settings = resolve_runtime_text_settings(get_ai_config=get_openai_compatible_config)
    wire_api = settings.wire_api.strip().lower()
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

    if wire_api == "responses":
        user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
        user_content.extend(build_image_content_parts(group_id, image_inputs, max_image_bytes=max_image_bytes))
        messages.append({"role": "user", "content": user_content})

    else:
        user_content = [{"type": "text", "text": user_prompt}]
        for image_part in build_image_content_parts(group_id, image_inputs, max_image_bytes=max_image_bytes):
            user_content.append({"type": "image_url", "image_url": {"url": image_part["image_url"]}})
        messages.append({"role": "user", "content": user_content if len(user_content) > 1 else user_prompt})

    request = build_runtime_ai_text_request(
        messages,
        settings=settings,
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=180,
    )
    return (
        call_ai_text(request).strip(),
        request.model,
    )
