"""Image input validation for stock topic analysis."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Tuple


MAX_EXTRACT_IMAGE_BYTES = 4 * 1024 * 1024
SUPPORTED_EXTRACT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def parse_image_data_url(image_data_url: str) -> Tuple[str, str, bytes]:
    value = _normalize_text(image_data_url)
    match = re.fullmatch(r"data:([^;,]+);base64,(.+)", value, flags=re.DOTALL)
    if not match:
        raise ValueError("图片数据格式不正确")

    mime_type = match.group(1).strip().lower()
    if mime_type not in SUPPORTED_EXTRACT_IMAGE_TYPES:
        raise ValueError("仅支持 JPG、PNG 或 WebP 图片")

    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise ValueError("图片 base64 数据不正确") from exc
    if not image_bytes:
        raise ValueError("图片内容为空")
    if len(image_bytes) > MAX_EXTRACT_IMAGE_BYTES:
        raise ValueError("图片不能超过 4MB")
    return mime_type, value, image_bytes
