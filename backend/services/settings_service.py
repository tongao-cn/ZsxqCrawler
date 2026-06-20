from __future__ import annotations

from collections.abc import Mapping

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


def apply_settings(target, values: Mapping[str, object], fields: tuple[str, ...]) -> None:
    for field in fields:
        setattr(target, field, values[field])


def settings_update_response(message: str, settings: dict) -> dict:
    return {
        "message": message,
        "settings": settings,
    }


def get_runtime_settings(scope: str) -> dict:
    if scope == "crawl":
        return default_crawl_settings()
    if scope == "crawler":
        return _get_crawler_settings()
    if scope == "downloader":
        return _get_downloader_settings()
    raise ValueError(f"Unknown settings scope: {scope}")


def update_runtime_settings(scope: str, values: Mapping[str, object]) -> dict:
    if scope == "crawl":
        return _update_crawl_settings(values)
    if scope == "crawler":
        return _update_crawler_settings(values)
    if scope == "downloader":
        return _update_downloader_settings(values)
    raise ValueError(f"Unknown settings scope: {scope}")


def _update_crawl_settings(settings: Mapping[str, object]) -> dict:
    return {"success": True, "message": "爬取设置已更新"}


def _get_crawler_settings() -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        return default_crawler_settings()

    return settings_from_attrs(crawler, CRAWLER_SETTING_FIELDS)


def _update_crawler_settings(values: Mapping[str, object]) -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        raise SettingsServiceError(404, "爬虫未初始化")

    if values["min_delay"] >= values["max_delay"]:
        raise SettingsServiceError(400, "最小延迟必须小于最大延迟")

    apply_settings(crawler, values, CRAWLER_SETTING_FIELDS)

    return settings_update_response(
        "爬虫设置已更新",
        settings_from_attrs(crawler, CRAWLER_SETTING_FIELDS),
    )


def _get_downloader_settings() -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        return default_downloader_settings()

    downloader = crawler.get_file_downloader()
    return settings_from_attrs(downloader, DOWNLOADER_SETTING_FIELDS)


def _update_downloader_settings(values: Mapping[str, object]) -> dict:
    crawler = get_crawler_safe()
    if not crawler:
        raise SettingsServiceError(404, "爬虫未初始化")

    if values["download_interval_min"] >= values["download_interval_max"]:
        raise SettingsServiceError(400, "最小下载间隔必须小于最大下载间隔")

    if values["long_delay_min"] >= values["long_delay_max"]:
        raise SettingsServiceError(400, "最小长休眠时间必须小于最大长休眠时间")

    downloader = crawler.get_file_downloader()

    apply_settings(downloader, values, DOWNLOADER_SETTING_FIELDS)

    return settings_update_response(
        "下载器设置已更新",
        settings_from_attrs(downloader, DOWNLOADER_SETTING_FIELDS),
    )
