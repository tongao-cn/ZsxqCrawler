from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from backend.services.media_service import (
    MediaBytes,
    MediaServiceError,
    clear_image_cache_response,
    get_image_cache_info_response,
    get_local_image_media,
    get_local_video_file,
    get_proxy_image,
)

router = APIRouter(prefix="/api", tags=["media"])


def _media_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


def _media_bytes_response(media: MediaBytes) -> Response:
    return Response(
        content=media.content,
        media_type=media.media_type,
        headers=media.headers,
    )


def _media_service_error(error: MediaServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/proxy-image")
async def proxy_image(url: str, group_id: Optional[str] = None):
    """代理图片请求，支持本地缓存"""
    try:
        return _media_bytes_response(get_proxy_image(url, group_id))
    except MediaServiceError as e:
        raise _media_service_error(e)
    except Exception as e:
        raise _media_route_error("代理图片失败", e)


@router.get("/proxy/image")
async def proxy_image_compat(url: str, group_id: Optional[str] = None):
    return await proxy_image(url=url, group_id=group_id)


@router.get("/cache/images/info/{group_id}")
async def get_image_cache_info(group_id: str):
    """获取指定群组的图片缓存统计信息"""
    try:
        return get_image_cache_info_response(group_id)
    except Exception as e:
        raise _media_route_error("获取缓存信息失败", e)


@router.delete("/cache/images/{group_id}")
async def clear_image_cache(group_id: str):
    """清空指定群组的图片缓存"""
    try:
        return clear_image_cache_response(group_id)
    except MediaServiceError as e:
        raise _media_route_error("清空缓存失败", _media_service_error(e))
    except Exception as e:
        raise _media_route_error("清空缓存失败", e)


@router.get("/groups/{group_id}/images/{image_path:path}")
async def get_local_image(group_id: str, image_path: str):
    """获取群组本地缓存的图片"""
    try:
        return _media_bytes_response(get_local_image_media(group_id, image_path))
    except MediaServiceError as e:
        raise _media_service_error(e)
    except Exception as e:
        raise _media_route_error("获取图片失败", e)


@router.get("/groups/{group_id}/videos/{video_path:path}")
async def get_local_video(group_id: str, video_path: str):
    """获取群组本地缓存的视频（支持范围请求，用于视频流播放）"""
    try:
        video_file = get_local_video_file(group_id, video_path)
        return FileResponse(
            path=str(video_file.path),
            media_type=video_file.media_type,
            filename=video_file.filename,
        )
    except MediaServiceError as e:
        raise _media_service_error(e)
    except Exception as e:
        raise _media_route_error("获取视频失败", e)
