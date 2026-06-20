from __future__ import annotations

from backend.core.crawler_runtime import get_crawler_safe

CRAWLER_SETTING_FIELDS = (
    "min_delay",
    "max_delay",
    "long_delay_interval",
    "timestamp_offset_ms",
    "debug_mode",
)

DOWNLOADER_SETTING_FIELDS = (
    "download_interval_min",
    "download_interval_max",
    "long_delay_interval",
    "long_delay_min",
    "long_delay_max",
)


class SettingsServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.status_code}: {self.detail}"


def default_crawl_settings() -> dict:
    return {
        "crawl_interval_min": 2.0,
        "crawl_interval_max": 5.0,
        "long_sleep_interval_min": 180.0,
        "long_sleep_interval_max": 300.0,
        "pages_per_batch": 15,
    }


def default_crawler_settings() -> dict:
    return {
        "min_delay": 2.0,
        "max_delay": 5.0,
        "long_delay_interval": 15,
        "timestamp_offset_ms": 1,
        "debug_mode": False,
    }


def default_downloader_settings() -> dict:
    return {
        "download_interval_min": 30,
        "download_interval_max": 60,
        "long_delay_interval": 10,
        "long_delay_min": 300,
        "long_delay_max": 600,
    }


def settings_from_attrs(source, fields: tuple[str, ...]) -> dict:
    return {field: getattr(source, field) for field in fields}


def apply_settings(target, request, fields: tuple[str, ...]) -> None:
    for field in fields:
        setattr(target, field, getattr(request, field))


def settings_update_response(message: str, settings: dict) -> dict:
    return {
        "message": message,
        "settings": settings,
    }


def get_crawl_settings_response() -> dict:
    return default_crawl_settings()


def update_crawl_settings_response(settings: dict) -> dict:
    return {"success": True, "message": "爬取设置已更新"}


def get_crawler_settings_response() -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        return default_crawler_settings()

    return settings_from_attrs(crawler, CRAWLER_SETTING_FIELDS)


def update_crawler_settings_response(request) -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        raise SettingsServiceError(404, "爬虫未初始化")

    if request.min_delay >= request.max_delay:
        raise SettingsServiceError(400, "最小延迟必须小于最大延迟")

    apply_settings(crawler, request, CRAWLER_SETTING_FIELDS)

    return settings_update_response(
        "爬虫设置已更新",
        settings_from_attrs(crawler, CRAWLER_SETTING_FIELDS),
    )


def get_downloader_settings_response() -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        return default_downloader_settings()

    downloader = crawler.get_file_downloader()
    return settings_from_attrs(downloader, DOWNLOADER_SETTING_FIELDS)


def update_downloader_settings_response(request) -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        raise SettingsServiceError(404, "爬虫未初始化")

    if request.download_interval_min >= request.download_interval_max:
        raise SettingsServiceError(400, "最小下载间隔必须小于最大下载间隔")

    if request.long_delay_min >= request.long_delay_max:
        raise SettingsServiceError(400, "最小长休眠时间必须小于最大长休眠时间")

    downloader = crawler.get_file_downloader()

    apply_settings(downloader, request, DOWNLOADER_SETTING_FIELDS)

    return settings_update_response(
        "下载器设置已更新",
        settings_from_attrs(downloader, DOWNLOADER_SETTING_FIELDS),
    )
