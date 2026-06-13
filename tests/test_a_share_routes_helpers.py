import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_A_SHARE_ROUTE_DEPS = (
    find_spec("fastapi") is not None
    and find_spec("pydantic") is not None
    and find_spec("requests") is not None
)


class AShareRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_task_metadata_preserves_group_field(self):
        from backend.routes.a_share_routes import _a_share_task_metadata

        self.assertEqual({"group_id": "51111112855254"}, _a_share_task_metadata("51111112855254"))
        self.assertEqual({"group_id": None}, _a_share_task_metadata(None))

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_create_a_share_analysis_task_response_preserves_task_contract(self):
        from backend.routes.a_share_routes import (
            TASK_CREATED_MESSAGE,
            AShareAnalysisRunRequest,
            _create_a_share_analysis_task_response,
            run_a_share_analysis_task,
        )

        request = AShareAnalysisRunRequest(group_id="51111112855254", days=21)

        with (
            patch("backend.routes.a_share_routes.create_task", return_value="task-a-share") as create_task,
            patch("backend.routes.a_share_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_a_share_analysis_task_response(
                request,
                "51111112855254",
                "群组 51111112855254",
                "最近 21 天",
            )

        create_task.assert_called_once_with(
            "a_share_analysis",
            "A股公司分析（群组 51111112855254，最近 21 天）",
            metadata={"group_id": "51111112855254"},
        )
        enqueue_runtime_task.assert_called_once_with(run_a_share_analysis_task, "task-a-share", request)
        self.assertEqual({"task_id": "task-a-share", "message": TASK_CREATED_MESSAGE}, response)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_run_a_share_analysis_for_task_preserves_service_arguments(self):
        from backend.routes.a_share_routes import AShareAnalysisRunRequest, _run_a_share_analysis_for_task

        request = AShareAnalysisRunRequest(
            group_id="51111112855254",
            days=30,
            concurrency=4,
            model="model-a",
            api_base="https://api.example.test",
            wire_api="responses",
            reasoning_effort="low",
            start_date="2026-05-01",
            end_date="2026-05-07",
            reset_start_date="2026-05-02",
            reset_end_date="2026-05-03",
        )
        expected = {"ok": True}
        with (
            patch("backend.routes.a_share_routes.run_analysis", return_value=expected) as run_analysis,
            patch("backend.routes.a_share_routes.add_task_log") as add_task_log,
        ):
            result = _run_a_share_analysis_for_task("task-a-share", "51111112855254", request)

            self.assertEqual(expected, result)
            run_analysis.assert_called_once()
            _, call_kwargs = run_analysis.call_args
            self.assertEqual(30, call_kwargs["days"])
            self.assertEqual("51111112855254", call_kwargs["group_id"])
            self.assertEqual("model-a", call_kwargs["model"])
            self.assertEqual("https://api.example.test", call_kwargs["api_base"])
            self.assertEqual("responses", call_kwargs["wire_api"])
            self.assertEqual("low", call_kwargs["reasoning_effort"])
            self.assertEqual(4, call_kwargs["concurrency"])
            self.assertEqual("2026-05-01", call_kwargs["start_date"])
            self.assertEqual("2026-05-07", call_kwargs["end_date"])
            self.assertEqual("2026-05-02", call_kwargs["reset_start_date"])
            self.assertEqual("2026-05-03", call_kwargs["reset_end_date"])

            call_kwargs["log_callback"]("analysis log")

        add_task_log.assert_called_once_with("task-a-share", "analysis log")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_start_a_share_analysis_task_preserves_status_and_logs(self):
        from backend.routes.a_share_routes import AShareAnalysisRunRequest, _start_a_share_analysis_task

        request = AShareAnalysisRunRequest(
            days=30,
            concurrency=4,
            model="model-a",
            api_base="https://api.example.test",
            wire_api="responses",
            reasoning_effort="low",
            reset_start_date="2026-05-02",
            reset_end_date="2026-05-03",
        )

        with (
            patch("backend.routes.a_share_routes.update_task") as update_task,
            patch("backend.routes.a_share_routes.add_task_log") as add_task_log,
        ):
            description = _start_a_share_analysis_task(
                "task-a-share",
                None,
                "全局聚合",
                "最近 30 天",
                request,
            )

        self.assertEqual("开始A股公司分析（全局聚合），扫描最近 30 天数据", description)
        update_task.assert_called_once_with("task-a-share", "running", description)
        self.assertEqual(
            [
                ("task-a-share", f"🚀 {description}"),
                (
                    "task-a-share",
                    "⚙️ 参数: group_id=GLOBAL, concurrency=4, model=model-a, "
                    "api_base=https://api.example.test, wire_api=responses, reasoning_effort=low",
                ),
                ("task-a-share", "🧹 删除并重跑区间: 2026-05-02 ~ 2026-05-03"),
            ],
            [call.args for call in add_task_log.call_args_list],
        )

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
    def test_export_tdx_passes_group_name_to_service(self):
        from backend.routes import a_share_routes
        from backend.routes.a_share_routes import AShareAnalysisExportTdxRequest

        with patch.object(
            a_share_routes,
            "export_a_share_rankings_to_tdx",
            return_value={"group_id": "123", "blocks": []},
        ) as export_mock:
            import asyncio

            result = asyncio.run(
                a_share_routes.export_a_share_analysis_to_tdx(
                    AShareAnalysisExportTdxRequest(
                        group_id="123",
                        group_name="纪要又要",
                        start_date="2026-05-01",
                        end_date="2026-05-19",
                    )
                )
            )

        self.assertTrue(result["success"])
        export_mock.assert_called_once_with(
            "2026-05-01",
            "2026-05-19",
            group_id="123",
            group_name="纪要又要",
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

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_run_range_text_supports_explicit_date_range(self):
        from backend.routes.a_share_routes import AShareAnalysisRunRequest, _run_range_text

        self.assertEqual("最近 21 天", _run_range_text(AShareAnalysisRunRequest(days=21)))
        self.assertEqual(
            "2026-05-01 ~ 2026-05-07",
            _run_range_text(
                AShareAnalysisRunRequest(
                    days=21,
                    start_date="2026-05-01",
                    end_date="2026-05-07",
                )
            ),
        )

        with self.assertRaisesRegex(ValueError, "start_date 和 end_date 需要同时提供"):
            _run_range_text(AShareAnalysisRunRequest(days=21, start_date="2026-05-01"))

        with self.assertRaisesRegex(ValueError, "start_date 不能晚于 end_date"):
            _run_range_text(
                AShareAnalysisRunRequest(
                    days=21,
                    start_date="2026-05-08",
                    end_date="2026-05-07",
                )
            )


if __name__ == "__main__":
    unittest.main()
