import unittest
from unittest.mock import patch


class AShareAnalysisRunPlanTests(unittest.TestCase):
    def test_build_analysis_run_plan_normalizes_inputs_and_paths(self):
        from backend.services.a_share_analysis_run_plan import build_analysis_run_plan

        with patch(
            "backend.services.a_share_analysis_run_plan.resolve_analysis_paths",
            return_value=("resolved.csv", "resolved.json"),
        ) as resolve_paths:
            plan = build_analysis_run_plan(
                days=0,
                concurrency=0,
                output_path="out.csv",
                state_path="state.json",
                group_id=" 511 ",
                start_date="2026-05-07",
                end_date="2026-05-08",
            )

        self.assertEqual(1, plan.days)
        self.assertEqual(1, plan.concurrency)
        self.assertEqual("511", plan.normalized_group_id)
        self.assertEqual("resolved.csv", plan.output_path)
        self.assertEqual("resolved.json", plan.state_path)
        self.assertEqual(("2026-05-07", "2026-05-08"), plan.run_date_range)
        resolve_paths.assert_called_once_with("out.csv", "state.json", "511")

    def test_build_analysis_run_plan_requires_complete_date_range(self):
        from backend.services.a_share_analysis_run_plan import build_analysis_run_plan

        with self.assertRaisesRegex(ValueError, "start_date 和 end_date 需要同时提供"):
            build_analysis_run_plan(days=1, concurrency=1, group_id="511", start_date="2026-05-07")

        with self.assertRaisesRegex(ValueError, "start_date 不能晚于 end_date"):
            build_analysis_run_plan(
                days=1,
                concurrency=1,
                group_id="511",
                start_date="2026-05-08",
                end_date="2026-05-07",
            )

    def test_discover_analysis_groups_uses_requested_group_or_cached_groups(self):
        from backend.services.a_share_analysis_run_plan import discover_analysis_groups

        self.assertEqual(["511"], discover_analysis_groups("511"))
        self.assertEqual(
            ["101", "202"],
            discover_analysis_groups(None, load_local_group_ids=lambda **_kwargs: {"202", "101"}),
        )

    def test_load_analysis_run_items_selects_date_range_or_last_days_reader(self):
        from backend.services.a_share_analysis_run_plan import load_analysis_run_items

        last_days_calls = []
        date_range_calls = []

        def read_last_days(group_id, days, log_callback):
            last_days_calls.append((group_id, days, log_callback))
            return [{"group_id": group_id, "mode": "last-days"}]

        def read_date_range(group_id, start_date, end_date, log_callback):
            date_range_calls.append((group_id, start_date, end_date, log_callback))
            return [{"group_id": group_id, "mode": "date-range"}]

        self.assertEqual(
            [
                {"group_id": "101", "mode": "last-days"},
                {"group_id": "202", "mode": "last-days"},
            ],
            load_analysis_run_items(
                ["101", "202"],
                days=7,
                run_date_range=None,
                read_topics_last_days=read_last_days,
                read_topics_in_date_range=read_date_range,
                log_callback="log",
            ),
        )
        self.assertEqual([("101", 7, "log"), ("202", 7, "log")], last_days_calls)

        self.assertEqual(
            [{"group_id": "101", "mode": "date-range"}],
            load_analysis_run_items(
                ["101"],
                days=7,
                run_date_range=("2026-05-01", "2026-05-02"),
                read_topics_last_days=read_last_days,
                read_topics_in_date_range=read_date_range,
                log_callback=None,
            ),
        )
        self.assertEqual([("101", "2026-05-01", "2026-05-02", None)], date_range_calls)


if __name__ == "__main__":
    unittest.main()
