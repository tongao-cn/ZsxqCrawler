from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from backend.core.db_path_manager import get_db_path_manager
from backend.core.image_cache_manager import (
    TRUSTED_IMAGE_HOSTNAMES,
    get_image_cache_manager,
    is_blocked_remote_ip,
    validate_remote_image_url,
)
from backend.core.account_context import get_cookie_for_group

_is_blocked_proxy_ip = is_blocked_remote_ip

router = APIRouter(prefix="/api", tags=["media"])


def _guess_content_type(path: Path, default: str) -> str:
    return mimetypes.guess_type(str(path))[0] or default


def _read_file_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _media_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


def _build_cached_image_response(cached_path: Path, cache_status: str) -> Response:
    return Response(
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
        raise HTTPException(status_code=403, detail="禁止访问该路径")
    return resolved_path


def _existing_local_media_path(base_dir: Path, child_path: str, missing_detail: str) -> Path:
    media_file = _resolve_safe_child_path(base_dir, child_path)
    if not media_file.exists():
        raise HTTPException(status_code=404, detail=missing_detail)
    return media_file


def _validate_proxy_image_url(url: str) -> str:
    try:
        return validate_remote_image_url(url)
    except ValueError as exc:
        detail = str(exc)
    if "http/https" in detail or "无法解析" in detail:
        raise HTTPException(status_code=400, detail="只允许代理 http/https 图片 URL")
    raise HTTPException(status_code=403, detail="禁止代理内网或本机图片 URL")


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


@router.get("/proxy-image")
async def proxy_image(url: str, group_id: Optional[str] = None):
    """代理图片请求，支持本地缓存"""
    try:
        safe_url = _validate_proxy_image_url(url)
        cache_manager = get_image_cache_manager(group_id)

        if cache_manager.is_cached(safe_url):
            cached_path = cache_manager.get_cached_path(safe_url)
            if cached_path and cached_path.exists():
                return _build_cached_image_response(cached_path, "HIT")

        success, cached_path, error = cache_manager.download_and_cache(
            safe_url,
            request_headers=_build_proxy_image_request_headers(group_id, safe_url),
        )

        if success and cached_path and cached_path.exists():
            return _build_cached_image_response(cached_path, "MISS")

        raise HTTPException(status_code=404, detail=f"图片加载失败: {error}")
    except HTTPException:
        raise
    except Exception as e:
        raise _media_route_error("代理图片失败", e)


@router.get("/proxy/image")
async def proxy_image_compat(url: str, group_id: Optional[str] = None):
    return await proxy_image(url=url, group_id=group_id)


@router.get("/cache/images/info/{group_id}")
async def get_image_cache_info(group_id: str):
    """获取指定群组的图片缓存统计信息"""
    try:
        cache_manager = get_image_cache_manager(group_id)
        return cache_manager.get_cache_info()
    except Exception as e:
        raise _media_route_error("获取缓存信息失败", e)


@router.delete("/cache/images/{group_id}")
async def clear_image_cache(group_id: str):
    """清空指定群组的图片缓存"""
    try:
        cache_manager = get_image_cache_manager(group_id)
        success, message = cache_manager.clear_cache()

        if success:
            return {"success": True, "message": message}
        raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        raise _media_route_error("清空缓存失败", e)


@router.get("/groups/{group_id}/images/{image_path:path}")
async def get_local_image(group_id: str, image_path: str):
    """获取群组本地缓存的图片"""
    try:
        path_manager = get_db_path_manager()
        group_dir = path_manager.get_group_data_dir(group_id)
        images_dir = Path(group_dir) / "images"

        image_file = _existing_local_media_path(images_dir, image_path, "图片不存在")
        content_type = _guess_content_type(image_file, "application/octet-stream")
        return Response(content=_read_file_bytes(image_file), media_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        raise _media_route_error("获取图片失败", e)


@router.get("/groups/{group_id}/videos/{video_path:path}")
async def get_local_video(group_id: str, video_path: str):
    """获取群组本地缓存的视频（支持范围请求，用于视频流播放）"""
    try:
        path_manager = get_db_path_manager()
        group_dir = path_manager.get_group_dir(group_id)
        videos_dir = Path(group_dir) / "column_videos"

        video_file = _existing_local_media_path(videos_dir, video_path, "视频不存在")
        content_type = _guess_content_type(video_file, "video/mp4")
        return FileResponse(
            path=str(video_file),
            media_type=content_type,
            filename=video_file.name,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _media_route_error("获取视频失败", e)
