from __future__ import annotations

import mimetypes
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

router = APIRouter(prefix="/api", tags=["media"])


def _main_module():
    return sys.modules.get("main") or sys.modules.get("__main__")


def _get_main_attr(name: str):
    module = _main_module()
    if module is None or not hasattr(module, name):
        raise RuntimeError(f"主模块未初始化，无法访问 {name}")
    return getattr(module, name)


@router.get("/proxy-image")
async def proxy_image(url: str, group_id: Optional[str] = None):
    """代理图片请求，支持本地缓存"""
    try:
        cache_manager = _get_main_attr("get_image_cache_manager")(group_id)

        if cache_manager.is_cached(url):
            cached_path = cache_manager.get_cached_path(url)
            if cached_path and cached_path.exists():
                content_type = mimetypes.guess_type(str(cached_path))[0] or "image/jpeg"
                with open(cached_path, "rb") as f:
                    content = f.read()

                return Response(
                    content=content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "Access-Control-Allow-Origin": "*",
                        "X-Cache-Status": "HIT",
                    },
                )

        success, cached_path, error = cache_manager.download_and_cache(url)

        if success and cached_path and cached_path.exists():
            content_type = mimetypes.guess_type(str(cached_path))[0] or "image/jpeg"
            with open(cached_path, "rb") as f:
                content = f.read()

            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                    "X-Cache-Status": "MISS",
                },
            )

        raise HTTPException(status_code=404, detail=f"图片加载失败: {error}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理图片失败: {str(e)}")


@router.get("/proxy/image")
async def proxy_image_compat(url: str, group_id: Optional[str] = None):
    return await proxy_image(url=url, group_id=group_id)


@router.get("/cache/images/info/{group_id}")
async def get_image_cache_info(group_id: str):
    """获取指定群组的图片缓存统计信息"""
    try:
        cache_manager = _get_main_attr("get_image_cache_manager")(group_id)
        return cache_manager.get_cache_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取缓存信息失败: {str(e)}")


@router.delete("/cache/images/{group_id}")
async def clear_image_cache(group_id: str):
    """清空指定群组的图片缓存"""
    try:
        cache_manager = _get_main_attr("get_image_cache_manager")(group_id)
        success, message = cache_manager.clear_cache()

        if success:
            return {"success": True, "message": message}
        raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空缓存失败: {str(e)}")


@router.get("/groups/{group_id}/images/{image_path:path}")
async def get_local_image(group_id: str, image_path: str):
    """获取群组本地缓存的图片"""
    try:
        path_manager = _get_main_attr("get_db_path_manager")()
        group_dir = path_manager.get_group_data_dir(group_id)
        images_dir = Path(group_dir) / "images"

        image_file = (images_dir / image_path).resolve()
        if not str(image_file).startswith(str(images_dir.resolve())):
            raise HTTPException(status_code=403, detail="禁止访问该路径")

        if not image_file.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        content_type = mimetypes.guess_type(str(image_file))[0] or "application/octet-stream"
        with open(image_file, "rb") as f:
            content = f.read()

        return Response(content=content, media_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")


@router.get("/groups/{group_id}/videos/{video_path:path}")
async def get_local_video(group_id: str, video_path: str):
    """获取群组本地缓存的视频（支持范围请求，用于视频流播放）"""
    try:
        path_manager = _get_main_attr("get_db_path_manager")()
        group_dir = path_manager.get_group_dir(group_id)
        videos_dir = Path(group_dir) / "column_videos"

        video_file = (videos_dir / video_path).resolve()
        if not str(video_file).startswith(str(videos_dir.resolve())):
            raise HTTPException(status_code=403, detail="禁止访问该路径")

        if not video_file.exists():
            raise HTTPException(status_code=404, detail="视频不存在")

        content_type = mimetypes.guess_type(str(video_file))[0] or "video/mp4"
        return FileResponse(
            path=str(video_file),
            media_type=content_type,
            filename=video_file.name,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取视频失败: {str(e)}")
