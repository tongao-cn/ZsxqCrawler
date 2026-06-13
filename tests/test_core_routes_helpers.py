import unittest
from importlib.util import find_spec


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


if __name__ == "__main__":
    unittest.main()
