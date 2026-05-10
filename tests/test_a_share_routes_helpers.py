import unittest
from importlib.util import find_spec


HAS_A_SHARE_ROUTE_DEPS = (
    find_spec("fastapi") is not None
    and find_spec("pydantic") is not None
    and find_spec("requests") is not None
)


class AShareRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_normalize_group_scope_keeps_existing_labels(self):
        from backend.routes.a_share_routes import _normalize_group_scope

        self.assertEqual((None, "全局聚合"), _normalize_group_scope(None))
        self.assertEqual((None, "全局聚合"), _normalize_group_scope("  "))
        self.assertEqual(("12345", "群组 12345"), _normalize_group_scope(" 12345 "))
        self.assertEqual(("67890", "群组 67890"), _normalize_group_scope(67890))

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_analysis_defaults_payload_matches_endpoint_shape(self):
        from backend.routes.a_share_routes import (
            A_SHARE_DEFAULT_API_BASE,
            A_SHARE_DEFAULT_CONCURRENCY,
            A_SHARE_DEFAULT_MODEL,
            A_SHARE_DEFAULT_RANKING_WINDOWS,
            A_SHARE_DEFAULT_REASONING_EFFORT,
            A_SHARE_DEFAULT_WIRE_API,
            _analysis_defaults_payload,
        )

        self.assertEqual(
            {
                "days": 21,
                "concurrency": A_SHARE_DEFAULT_CONCURRENCY,
                "model": A_SHARE_DEFAULT_MODEL,
                "api_base": A_SHARE_DEFAULT_API_BASE,
                "wire_api": A_SHARE_DEFAULT_WIRE_API,
                "reasoning_effort": A_SHARE_DEFAULT_REASONING_EFFORT,
                "ranking_windows": list(A_SHARE_DEFAULT_RANKING_WINDOWS),
            },
            _analysis_defaults_payload(),
        )

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_bounded_chart_top_n_clamps_to_existing_range(self):
        from backend.routes.a_share_routes import _bounded_chart_top_n

        self.assertEqual(1, _bounded_chart_top_n(-5))
        self.assertEqual(1, _bounded_chart_top_n(0))
        self.assertEqual(20, _bounded_chart_top_n(20))
        self.assertEqual(100, _bounded_chart_top_n(101))

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_success_payload_preserves_existing_merge_order(self):
        from backend.routes.a_share_routes import _success_payload

        self.assertEqual({"success": True, "deleted": 3}, _success_payload({"deleted": 3}))
        self.assertEqual({"success": False, "error": "kept"}, _success_payload({"success": False, "error": "kept"}))


if __name__ == "__main__":
    unittest.main()
