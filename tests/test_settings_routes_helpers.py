import unittest
from types import SimpleNamespace

from backend.routes.settings_routes import (
    _CRAWLER_SETTING_FIELDS,
    _DOWNLOADER_SETTING_FIELDS,
    _apply_settings,
    _default_crawl_settings,
    _default_crawler_settings,
    _default_downloader_settings,
    _settings_from_attrs,
    _settings_update_response,
    _update_crawl_settings_response,
    update_crawl_settings,
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


if __name__ == "__main__":
    unittest.main()
