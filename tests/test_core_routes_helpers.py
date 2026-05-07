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
    def test_add_table_counts_accumulates_missing_and_zero_values(self):
        from backend.routes.core_routes import _add_table_counts

        counts = {"topics": 2}

        _add_table_counts(counts, {"topics": "3", "comments": None})
        _add_table_counts(counts, None)

        self.assertEqual({"topics": 5, "comments": 0}, counts)

    @unittest.skipUnless(HAS_CORE_ROUTE_DEPS, "core route dependencies are not installed")
    def test_merge_timestamp_info_aggregates_bounds_and_totals(self):
        from backend.routes.core_routes import _merge_timestamp_info

        target = {
            "total_topics": 0,
            "oldest_timestamp": "",
            "newest_timestamp": "",
            "has_data": False,
        }

        _merge_timestamp_info(
            target,
            {
                "has_data": True,
                "oldest_timestamp": "2026-05-03T00:00:00",
                "newest_timestamp": "2026-05-04T00:00:00",
                "total_topics": "2",
            },
        )
        _merge_timestamp_info(
            target,
            {
                "has_data": True,
                "oldest_timestamp": "2026-05-01T00:00:00",
                "newest_timestamp": "2026-05-06T00:00:00",
                "total_topics": 3,
            },
        )
        _merge_timestamp_info(target, {"has_data": False, "total_topics": 99})

        self.assertEqual(
            {
                "total_topics": 5,
                "oldest_timestamp": "2026-05-01T00:00:00",
                "newest_timestamp": "2026-05-06T00:00:00",
                "has_data": True,
            },
            target,
        )


if __name__ == "__main__":
    unittest.main()
