import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_CORE_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class CoreRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_empty_database_stats_response_keeps_endpoint_shape(self):
        from backend.routes.core_routes import _empty_database_stats_response

        self.assertEqual(
            {
                "configured": False,
                "topic_database": {
                    "stats": {},
                    "timestamp_info": {
                        "total_topics": 0,
                        "oldest_timestamp": "",
                        "newest_timestamp": "",
                        "has_data": False,
                    },
                },
                "file_database": {
                    "stats": {},
                },
            },
            _empty_database_stats_response(False),
        )
        self.assertTrue(_empty_database_stats_response(True)["configured"])

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_masked_config_cookie_preserves_existing_placeholder_semantics(self):
        from backend.routes.core_routes import _masked_config_cookie

        self.assertEqual("未配置", _masked_config_cookie(""))
        self.assertEqual("未配置", _masked_config_cookie("your_cookie_here"))
        self.assertEqual("***", _masked_config_cookie("zsxq_access_token=secret"))

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_core_route_error_preserves_status_and_detail_format(self):
        from backend.routes.core_routes import _core_route_error

        error = _core_route_error("获取配置失败", RuntimeError("boom"))

        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.detail, "获取配置失败: boom")

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_get_config_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes.core_routes import get_config

        with patch("backend.routes.core_routes.get_public_config", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(get_config())

        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "获取配置失败: boom")

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_update_config_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes.core_routes import ConfigModel, update_config

        with patch("backend.routes.core_routes.update_auth_config", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(update_config(ConfigModel(cookie="zsxq_access_token=secret")))

        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "更新配置失败: boom")

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_config_routes_delegate_to_service(self):
        import asyncio

        from backend.routes import core_routes

        with patch.object(core_routes, "get_public_config", return_value={"configured": True}) as get_public:
            result = asyncio.run(core_routes.get_config())

        self.assertEqual({"configured": True}, result)
        get_public.assert_called_once_with()

        with patch.object(core_routes, "update_auth_config", return_value={"success": True}) as update_auth:
            result = asyncio.run(core_routes.update_config(core_routes.ConfigModel(cookie="cookie-1")))

        self.assertEqual({"success": True}, result)
        update_auth.assert_called_once_with("cookie-1")

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_get_database_stats_route_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes.core_routes import get_database_stats

        with patch("backend.routes.core_routes.get_global_database_stats_read_model", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(get_database_stats())

        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "获取数据库统计失败: boom")

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_get_database_stats_route_offloads_read_model_to_thread(self):
        import asyncio

        from backend.routes import core_routes

        async def fake_to_thread(func, *args):
            return {"called": func.__name__, "args": args}

        with patch.object(core_routes.asyncio, "to_thread", side_effect=fake_to_thread):
            result = asyncio.run(core_routes.get_database_stats())

        self.assertEqual({"called": "get_global_database_stats_read_model", "args": ()}, result)


if __name__ == "__main__":
    unittest.main()
