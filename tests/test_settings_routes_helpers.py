import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.routes.settings_routes import (
    _CRAWLER_SETTING_FIELDS,
    _DOWNLOADER_SETTING_FIELDS,
    _apply_settings,
    _default_crawl_settings,
    _default_crawler_settings,
    _default_downloader_settings,
    _get_crawl_settings_response,
    _get_crawler_settings_response,
    _get_downloader_settings_response,
    _settings_from_attrs,
    _settings_update_response,
    _update_crawl_settings_response,
    _update_crawler_settings_response,
    CrawlerSettingsRequest,
    get_crawl_settings,
    get_crawler_settings,
    get_downloader_settings,
    update_crawl_settings,
    update_crawler_settings,
)


class SettingsRoutesHelpersTest(unittest.TestCase):
    def test_default_settings_payloads_match_existing_values(self):
        self.assertEqual(
            _default_crawl_settings(),
            {
                "crawl_interval_min": 2.0,
                "crawl_interval_max": 5.0,
                "long_sleep_interval_min": 180.0,
                "long_sleep_interval_max": 300.0,
                "pages_per_batch": 15,
            },
        )
        self.assertEqual(
            _default_crawler_settings(),
            {
                "min_delay": 2.0,
                "max_delay": 5.0,
                "long_delay_interval": 15,
                "timestamp_offset_ms": 1,
                "debug_mode": False,
            },
        )
        self.assertEqual(
            _default_downloader_settings(),
            {
                "download_interval_min": 30,
                "download_interval_max": 60,
                "long_delay_interval": 10,
                "long_delay_min": 300,
                "long_delay_max": 600,
            },
        )

    def test_settings_from_attrs_keeps_declared_field_order(self):
        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=True,
            unrelated="ignored",
        )

        self.assertEqual(
            _settings_from_attrs(crawler, _CRAWLER_SETTING_FIELDS),
            {
                "min_delay": 1.5,
                "max_delay": 6.0,
                "long_delay_interval": 20,
                "timestamp_offset_ms": 7,
                "debug_mode": True,
            },
        )

    def test_apply_settings_updates_only_declared_fields(self):
        downloader = SimpleNamespace(
            download_interval_min=30,
            download_interval_max=60,
            long_delay_interval=10,
            long_delay_min=300,
            long_delay_max=600,
            keep_me="unchanged",
        )
        request = SimpleNamespace(
            download_interval_min=5,
            download_interval_max=25,
            long_delay_interval=3,
            long_delay_min=90,
            long_delay_max=180,
            keep_me="request value",
        )

        _apply_settings(downloader, request, _DOWNLOADER_SETTING_FIELDS)

        self.assertEqual(
            _settings_from_attrs(downloader, _DOWNLOADER_SETTING_FIELDS),
            {
                "download_interval_min": 5,
                "download_interval_max": 25,
                "long_delay_interval": 3,
                "long_delay_min": 90,
                "long_delay_max": 180,
            },
        )
        self.assertEqual(downloader.keep_me, "unchanged")

    def test_settings_update_response_keeps_payload_shape(self):
        settings = {"min_delay": 2.0}

        self.assertEqual(
            _settings_update_response("updated", settings),
            {
                "message": "updated",
                "settings": settings,
            },
        )

    def test_update_crawl_settings_route_preserves_fixed_success_response(self):
        import asyncio

        self.assertEqual(
            asyncio.run(update_crawl_settings({"ignored": "value"})),
            {"success": True, "message": "爬取设置已更新"},
        )

    def test_update_crawl_settings_response_preserves_fixed_success_response(self):
        self.assertEqual(
            _update_crawl_settings_response({"ignored": "value"}),
            {"success": True, "message": "爬取设置已更新"},
        )

    def test_get_crawl_settings_route_preserves_default_payload(self):
        import asyncio

        self.assertEqual(asyncio.run(get_crawl_settings()), _default_crawl_settings())

    def test_get_crawl_settings_response_preserves_default_payload(self):
        self.assertEqual(_get_crawl_settings_response(), _default_crawl_settings())

    def test_get_crawler_settings_route_preserves_default_when_uninitialized(self):
        import asyncio

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=None) as get_crawler:
            result = asyncio.run(get_crawler_settings())

        self.assertEqual(result, _default_crawler_settings())
        get_crawler.assert_called_once_with()

    def test_get_crawler_settings_route_preserves_runtime_attrs(self):
        import asyncio

        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=True,
        )

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler) as get_crawler:
            result = asyncio.run(get_crawler_settings())

        self.assertEqual(
            result,
            {
                "min_delay": 1.5,
                "max_delay": 6.0,
                "long_delay_interval": 20,
                "timestamp_offset_ms": 7,
                "debug_mode": True,
            },
        )
        get_crawler.assert_called_once_with()

    def test_get_crawler_settings_response_preserves_default_when_uninitialized(self):
        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=None) as get_crawler:
            result = _get_crawler_settings_response()

        self.assertEqual(result, _default_crawler_settings())
        get_crawler.assert_called_once_with()

    def test_get_crawler_settings_response_preserves_runtime_attrs(self):
        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=True,
        )

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler) as get_crawler:
            result = _get_crawler_settings_response()

        self.assertEqual(
            result,
            {
                "min_delay": 1.5,
                "max_delay": 6.0,
                "long_delay_interval": 20,
                "timestamp_offset_ms": 7,
                "debug_mode": True,
            },
        )
        get_crawler.assert_called_once_with()

    def test_update_crawler_settings_route_preserves_success_payload_and_side_effects(self):
        import asyncio

        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=False,
        )
        request = CrawlerSettingsRequest(
            min_delay=2.5,
            max_delay=6.5,
            long_delay_interval=30,
            timestamp_offset_ms=9,
            debug_mode=True,
        )

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler) as get_crawler:
            result = asyncio.run(update_crawler_settings(request))

        expected_settings = {
            "min_delay": 2.5,
            "max_delay": 6.5,
            "long_delay_interval": 30,
            "timestamp_offset_ms": 9,
            "debug_mode": True,
        }
        self.assertEqual(result, {"message": "爬虫设置已更新", "settings": expected_settings})
        self.assertEqual(_settings_from_attrs(crawler, _CRAWLER_SETTING_FIELDS), expected_settings)
        get_crawler.assert_called_once_with()

    def test_update_crawler_settings_route_preserves_wrapped_missing_crawler_error(self):
        import asyncio

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=None):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(update_crawler_settings(CrawlerSettingsRequest()))

        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "更新爬虫设置失败: 404: 爬虫未初始化")

    def test_update_crawler_settings_route_preserves_wrapped_invalid_delay_error(self):
        import asyncio

        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=False,
        )
        request = CrawlerSettingsRequest(min_delay=6.0, max_delay=6.0)

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(update_crawler_settings(request))

        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "更新爬虫设置失败: 400: 最小延迟必须小于最大延迟")
        self.assertEqual(crawler.min_delay, 1.5)

    def test_update_crawler_settings_response_preserves_success_payload_and_side_effects(self):
        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=False,
        )
        request = CrawlerSettingsRequest(
            min_delay=2.5,
            max_delay=6.5,
            long_delay_interval=30,
            timestamp_offset_ms=9,
            debug_mode=True,
        )

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler) as get_crawler:
            result = _update_crawler_settings_response(request)

        expected_settings = {
            "min_delay": 2.5,
            "max_delay": 6.5,
            "long_delay_interval": 30,
            "timestamp_offset_ms": 9,
            "debug_mode": True,
        }
        self.assertEqual(result, {"message": "爬虫设置已更新", "settings": expected_settings})
        self.assertEqual(_settings_from_attrs(crawler, _CRAWLER_SETTING_FIELDS), expected_settings)
        get_crawler.assert_called_once_with()

    def test_update_crawler_settings_response_preserves_missing_crawler_error(self):
        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=None):
            with self.assertRaises(HTTPException) as caught:
                _update_crawler_settings_response(CrawlerSettingsRequest())

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "爬虫未初始化")

    def test_update_crawler_settings_response_preserves_invalid_delay_error(self):
        crawler = SimpleNamespace(
            min_delay=1.5,
            max_delay=6.0,
            long_delay_interval=20,
            timestamp_offset_ms=7,
            debug_mode=False,
        )
        request = CrawlerSettingsRequest(min_delay=6.0, max_delay=6.0)

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler):
            with self.assertRaises(HTTPException) as caught:
                _update_crawler_settings_response(request)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, "最小延迟必须小于最大延迟")
        self.assertEqual(crawler.min_delay, 1.5)

    def test_get_downloader_settings_route_preserves_default_when_uninitialized(self):
        import asyncio

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=None) as get_crawler:
            result = asyncio.run(get_downloader_settings())

        self.assertEqual(result, _default_downloader_settings())
        get_crawler.assert_called_once_with()

    def test_get_downloader_settings_route_preserves_runtime_attrs(self):
        import asyncio

        downloader = SimpleNamespace(
            download_interval_min=4,
            download_interval_max=16,
            long_delay_interval=6,
            long_delay_min=120,
            long_delay_max=240,
        )
        crawler = SimpleNamespace(get_file_downloader=Mock(return_value=downloader))

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler) as get_crawler:
            result = asyncio.run(get_downloader_settings())

        self.assertEqual(
            result,
            {
                "download_interval_min": 4,
                "download_interval_max": 16,
                "long_delay_interval": 6,
                "long_delay_min": 120,
                "long_delay_max": 240,
            },
        )
        get_crawler.assert_called_once_with()
        crawler.get_file_downloader.assert_called_once_with()

    def test_get_downloader_settings_response_preserves_default_when_uninitialized(self):
        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=None) as get_crawler:
            result = _get_downloader_settings_response()

        self.assertEqual(result, _default_downloader_settings())
        get_crawler.assert_called_once_with()

    def test_get_downloader_settings_response_preserves_runtime_attrs(self):
        downloader = SimpleNamespace(
            download_interval_min=4,
            download_interval_max=16,
            long_delay_interval=6,
            long_delay_min=120,
            long_delay_max=240,
        )
        crawler = SimpleNamespace(get_file_downloader=Mock(return_value=downloader))

        with patch("backend.routes.settings_routes.get_crawler_safe", return_value=crawler) as get_crawler:
            result = _get_downloader_settings_response()

        self.assertEqual(
            result,
            {
                "download_interval_min": 4,
                "download_interval_max": 16,
                "long_delay_interval": 6,
                "long_delay_min": 120,
                "long_delay_max": 240,
            },
        )
        get_crawler.assert_called_once_with()
        crawler.get_file_downloader.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
