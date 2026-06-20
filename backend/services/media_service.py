from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from backend.core.account_context import get_cookie_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.core.image_cache_manager import (
    TRUSTED_IMAGE_HOSTNAMES,
    get_image_cache_manager,
    is_blocked_remote_ip,
    validate_remote_image_url,
)

_is_blocked_proxy_ip = is_blocked_remote_ip


@dataclass(frozen=True)
class MediaBytes:
    content: bytes
    media_type: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalMediaFile:
    path: Path
    media_type: str
    filename: str


class MediaServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _guess_content_type(path: Path, default: str) -> str:
    return mimetypes.guess_type(str(path))[0] or default


def _read_file_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _cached_image_media(cached_path: Path, cache_status: str) -> MediaBytes:
    return MediaBytes(
        content=_read_file_bytes(cached_path),
        media_type=_guess_content_type(cached_path, "image/jpeg"),
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "X-Cache-Status": cache_status,
        },
    )


def _resolve_safe_child_path(base_dir: Path, child_path: str) -> Path:
    base_path = base_dir.resolve()
    resolved_path = (base_path / child_path).resolve()
    try:
        resolved_path.relative_to(base_path)
    except ValueError:
        raise MediaServiceError(403, "禁止访问该路径")
    return resolved_path


def _existing_local_media_path(base_dir: Path, child_path: str, missing_detail: str) -> Path:
    media_file = _resolve_safe_child_path(base_dir, child_path)
    if not media_file.exists():
        raise MediaServiceError(404, missing_detail)
    return media_file


def _validate_proxy_image_url(url: str) -> str:
    try:
        return validate_remote_image_url(url)
    except ValueError as exc:
        detail = str(exc)
    if "http/https" in detail or "无法解析" in detail:
        raise MediaServiceError(400, "只允许代理 http/https 图片 URL")
    raise MediaServiceError(403, "禁止代理内网或本机图片 URL")


def _build_proxy_image_request_headers(group_id: Optional[str], url: str) -> dict[str, str]:
    if not group_id:
        return {}
    hostname = urlparse(url).hostname
    if not hostname or hostname.lower() not in TRUSTED_IMAGE_HOSTNAMES:
        return {}
    cookie = get_cookie_for_group(group_id)
    if not cookie:
        return {}
    return {"Cookie": cookie}


def get_proxy_image(url: str, group_id: Optional[str] = None) -> MediaBytes:
    safe_url = _validate_proxy_image_url(url)
    cache_manager = get_image_cache_manager(group_id)

    if cache_manager.is_cached(safe_url):
        cached_path = cache_manager.get_cached_path(safe_url)
        if cached_path and cached_path.exists():
            return _cached_image_media(cached_path, "HIT")

    success, cached_path, error = cache_manager.download_and_cache(
        safe_url,
        request_headers=_build_proxy_image_request_headers(group_id, safe_url),
    )

    if success and cached_path and cached_path.exists():
        return _cached_image_media(cached_path, "MISS")

    raise MediaServiceError(404, f"图片加载失败: {error}")


def get_image_cache_info_response(group_id: str) -> dict:
    cache_manager = get_image_cache_manager(group_id)
    return cache_manager.get_cache_info()


def clear_image_cache_response(group_id: str) -> dict:
    cache_manager = get_image_cache_manager(group_id)
    success, message = cache_manager.clear_cache()

    if success:
        return {"success": True, "message": message}
    raise MediaServiceError(500, message)


def get_local_image_media(group_id: str, image_path: str) -> MediaBytes:
    path_manager = get_db_path_manager()
    group_dir = path_manager.get_group_data_dir(group_id)
    images_dir = Path(group_dir) / "images"

    image_file = _existing_local_media_path(images_dir, image_path, "图片不存在")
    return MediaBytes(
        content=_read_file_bytes(image_file),
        media_type=_guess_content_type(image_file, "application/octet-stream"),
    )


def get_local_video_file(group_id: str, video_path: str) -> LocalMediaFile:
    path_manager = get_db_path_manager()
    group_dir = path_manager.get_group_dir(group_id)
    videos_dir = Path(group_dir) / "column_videos"

    video_file = _existing_local_media_path(videos_dir, video_path, "视频不存在")
    return LocalMediaFile(
        path=video_file,
        media_type=_guess_content_type(video_file, "video/mp4"),
        filename=video_file.name,
    )
