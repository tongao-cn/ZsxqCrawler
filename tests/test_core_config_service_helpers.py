import unittest
from unittest.mock import mock_open, patch


class CoreConfigServiceHelperTests(unittest.TestCase):
    def test_masked_config_cookie_preserves_existing_placeholder_semantics(self):
        from backend.services.core_config_service import masked_config_cookie

        self.assertEqual("未配置", masked_config_cookie(""))
        self.assertEqual("未配置", masked_config_cookie("your_cookie_here"))
        self.assertEqual("***", masked_config_cookie("zsxq_access_token=secret"))

    def test_get_public_config_masks_cookie_and_preserves_sections(self):
        from backend.services import core_config_service as service

        with (
            patch.object(
                service,
                "load_config",
                return_value={
                    "auth": {"cookie": "zsxq_access_token=secret"},
                    "database": {"postgres_dsn": "postgres://example"},
                    "download": {"dir": "downloads"},
                },
            ),
            patch.object(service, "is_configured", return_value=True),
        ):
            result = service.get_public_config()

        self.assertEqual(
            {
                "configured": True,
                "auth": {"cookie": "***"},
                "database": {"postgres_dsn": "postgres://example"},
                "download": {"dir": "downloads"},
            },
            result,
        )

    def test_get_public_config_preserves_empty_config_shape(self):
        from backend.services import core_config_service as service

        with patch.object(service, "load_config", return_value=None), patch.object(service, "is_configured", return_value=False):
            result = service.get_public_config()

        self.assertEqual(
            {
                "configured": False,
                "auth": {"cookie": "未配置"},
                "database": {},
                "download": {},
            },
            result,
        )

    def test_update_auth_config_preserves_existing_ai_values_and_clears_runtime(self):
        from backend.services import core_config_service as service

        opened = mock_open()

        with (
            patch.object(
                service,
                "load_config",
                return_value={
                    "ai": {
                        "model": "custom-model",
                        "api_base": "https://example.test/v1",
                        "wire_api": "chat_completions",
                        "reasoning_effort": "low",
                    }
                },
            ),
            patch("builtins.open", opened),
            patch.object(service, "clear_crawler_instance") as clear_runtime,
        ):
            result = service.update_auth_config("zsxq_access_token=test-cookie")

        opened.assert_called_once_with("config.toml", "w", encoding="utf-8")
        written = opened().write.call_args.args[0]

        self.assertIn('cookie = "zsxq_access_token=test-cookie"', written)
        self.assertIn('model = "custom-model"', written)
        self.assertIn('api_base = "https://example.test/v1"', written)
        self.assertIn('wire_api = "chat_completions"', written)
        self.assertIn('reasoning_effort = "low"', written)
        self.assertIn('api_key = ""', written)
        clear_runtime.assert_called_once_with()
        self.assertEqual({"message": "配置更新成功", "success": True}, result)

    def test_update_auth_config_uses_ai_defaults_when_existing_config_is_missing(self):
        from backend.services import core_config_service as service

        opened = mock_open()

        with (
            patch.object(service, "load_config", return_value={}),
            patch("builtins.open", opened),
            patch.object(service, "clear_crawler_instance"),
        ):
            service.update_auth_config("cookie-1")

        written = opened().write.call_args.args[0]

        self.assertIn(f'model = "{service.A_SHARE_DEFAULT_MODEL}"', written)
        self.assertIn(f'api_base = "{service.A_SHARE_DEFAULT_API_BASE}"', written)
        self.assertIn(f'wire_api = "{service.A_SHARE_DEFAULT_WIRE_API}"', written)
        self.assertIn(f'reasoning_effort = "{service.A_SHARE_DEFAULT_REASONING_EFFORT}"', written)
