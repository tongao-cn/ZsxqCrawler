from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.settings_service import (
    get_runtime_settings,
    update_runtime_settings,
)

router = APIRouter(prefix="/api", tags=["settings"])


def _settings_route_error(message: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {str(error)}")


class CrawlerSettingsRequest(BaseModel):
    min_delay: float = Field(default=2.0, ge=0.5, le=10.0)
    max_delay: float = Field(default=5.0, ge=1.0, le=20.0)
    long_delay_interval: int = Field(default=15, ge=5, le=100)
    timestamp_offset_ms: int = Field(default=1, ge=0, le=1000)
    debug_mode: bool = Field(default=False)


class DownloaderSettingsRequest(BaseModel):
    download_interval_min: int = Field(default=30, ge=1, le=300)
    download_interval_max: int = Field(default=60, ge=5, le=600)
    long_delay_interval: int = Field(default=10, ge=1, le=100)
    long_delay_min: int = Field(default=300, ge=60, le=1800)
    long_delay_max: int = Field(default=600, ge=120, le=3600)


@router.get("/settings/crawl")
async def get_crawl_settings():
    """获取话题爬取设置"""
    try:
        return get_runtime_settings("crawl")
    except Exception as e:
        raise _settings_route_error("获取爬取设置失败", e)


@router.post("/settings/crawl")
async def update_crawl_settings(settings: dict):
    """更新话题爬取设置"""
    try:
        return update_runtime_settings("crawl", settings)
    except Exception as e:
        raise _settings_route_error("更新爬取设置失败", e)


@router.get("/settings/crawler")
async def get_crawler_settings():
    """获取爬虫设置"""
    try:
        return get_runtime_settings("crawler")
    except Exception as e:
        raise _settings_route_error("获取爬虫设置失败", e)


@router.post("/settings/crawler")
async def update_crawler_settings(request: CrawlerSettingsRequest):
    """更新爬虫设置"""
    try:
        return update_runtime_settings("crawler", request.model_dump())
    except Exception as e:
        raise _settings_route_error("更新爬虫设置失败", e)


@router.get("/settings/downloader")
async def get_downloader_settings():
    """获取文件下载器设置"""
    try:
        return get_runtime_settings("downloader")
    except Exception as e:
        raise _settings_route_error("获取下载器设置失败", e)


@router.post("/settings/downloader")
async def update_downloader_settings(request: DownloaderSettingsRequest):
    """更新文件下载器设置"""
    try:
        return update_runtime_settings("downloader", request.model_dump())
    except Exception as e:
        raise _settings_route_error("更新下载器设置失败", e)
