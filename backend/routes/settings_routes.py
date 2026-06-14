from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.crawler_runtime import get_crawler_safe

router = APIRouter(prefix="/api", tags=["settings"])

_CRAWLER_SETTING_FIELDS = (
    "min_delay",
    "max_delay",
    "long_delay_interval",
    "timestamp_offset_ms",
    "debug_mode",
)

_DOWNLOADER_SETTING_FIELDS = (
    "download_interval_min",
    "download_interval_max",
    "long_delay_interval",
    "long_delay_min",
    "long_delay_max",
)


def _default_crawl_settings() -> dict:
    return {
        "crawl_interval_min": 2.0,
        "crawl_interval_max": 5.0,
        "long_sleep_interval_min": 180.0,
        "long_sleep_interval_max": 300.0,
        "pages_per_batch": 15,
    }


def _default_crawler_settings() -> dict:
    return {
        "min_delay": 2.0,
        "max_delay": 5.0,
        "long_delay_interval": 15,
        "timestamp_offset_ms": 1,
        "debug_mode": False,
    }


def _default_downloader_settings() -> dict:
    return {
        "download_interval_min": 30,
        "download_interval_max": 60,
        "long_delay_interval": 10,
        "long_delay_min": 300,
        "long_delay_max": 600,
    }


def _settings_from_attrs(source, fields: tuple[str, ...]) -> dict:
    return {field: getattr(source, field) for field in fields}


def _apply_settings(target, request, fields: tuple[str, ...]) -> None:
    for field in fields:
        setattr(target, field, getattr(request, field))


def _settings_update_response(message: str, settings: dict) -> dict:
    return {
        "message": message,
        "settings": settings,
    }


def _update_crawl_settings_response(settings: dict) -> dict:
    return {"success": True, "message": "爬取设置已更新"}


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
        return _default_crawl_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取爬取设置失败: {str(e)}")


@router.post("/settings/crawl")
async def update_crawl_settings(settings: dict):
    """更新话题爬取设置"""
    try:
        return _update_crawl_settings_response(settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新爬取设置失败: {str(e)}")


@router.get("/settings/crawler")
async def get_crawler_settings():
    """获取爬虫设置"""
    try:
        crawler = get_crawler_safe()
        if not crawler:
            return _default_crawler_settings()

        return _settings_from_attrs(crawler, _CRAWLER_SETTING_FIELDS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取爬虫设置失败: {str(e)}")


@router.post("/settings/crawler")
async def update_crawler_settings(request: CrawlerSettingsRequest):
    """更新爬虫设置"""
    try:
        crawler = get_crawler_safe()
        if not crawler:
            raise HTTPException(status_code=404, detail="爬虫未初始化")

        if request.min_delay >= request.max_delay:
            raise HTTPException(status_code=400, detail="最小延迟必须小于最大延迟")

        _apply_settings(crawler, request, _CRAWLER_SETTING_FIELDS)

        return _settings_update_response(
            "爬虫设置已更新",
            _settings_from_attrs(crawler, _CRAWLER_SETTING_FIELDS),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新爬虫设置失败: {str(e)}")


@router.get("/settings/downloader")
async def get_downloader_settings():
    """获取文件下载器设置"""
    try:
        crawler = get_crawler_safe()
        if not crawler:
            return _default_downloader_settings()

        downloader = crawler.get_file_downloader()
        return _settings_from_attrs(downloader, _DOWNLOADER_SETTING_FIELDS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取下载器设置失败: {str(e)}")


@router.post("/settings/downloader")
async def update_downloader_settings(request: DownloaderSettingsRequest):
    """更新文件下载器设置"""
    try:
        crawler = get_crawler_safe()
        if not crawler:
            raise HTTPException(status_code=404, detail="爬虫未初始化")

        if request.download_interval_min >= request.download_interval_max:
            raise HTTPException(status_code=400, detail="最小下载间隔必须小于最大下载间隔")

        if request.long_delay_min >= request.long_delay_max:
            raise HTTPException(status_code=400, detail="最小长休眠时间必须小于最大长休眠时间")

        downloader = crawler.get_file_downloader()

        _apply_settings(downloader, request, _DOWNLOADER_SETTING_FIELDS)

        return _settings_update_response(
            "下载器设置已更新",
            _settings_from_attrs(downloader, _DOWNLOADER_SETTING_FIELDS),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新下载器设置失败: {str(e)}")
