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
    def test_a_share_route_error_preserves_status_and_detail_format(self):
        from backend.routes.a_share_routes import _a_share_route_error

        error = _a_share_route_error("获取A股分析状态失败", RuntimeError("route boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取A股分析状态失败: route boom", error.detail)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_create_a_share_analysis_task_response_delegates_to_workflow_launch(self):
        from backend.routes.a_share_routes import AShareAnalysisRunRequest, _create_a_share_analysis_task_response

        request = AShareAnalysisRunRequest(
            group_id="51111112855254",
            days=14,
            concurrency=2,
            model="test-model",
            api_base="https://example.test/v1",
            wire_api="chat_completions",
            reasoning_effort="low",
            start_date="2026-05-01",
            end_date="2026-05-07",
            reset_start_date="2026-05-01",
            reset_end_date="2026-05-02",
        )

        with patch(
            "backend.routes.a_share_routes.create_a_share_analysis_task",
            return_value={"task_id": "task-a-share", "message": "任务已创建，正在后台执行"},
        ) as create_task:
            response = _create_a_share_analysis_task_response(request)

        create_task.assert_called_once_with(
            group_id="51111112855254",
            days=14,
            concurrency=2,
            model="test-model",
            api_base="https://example.test/v1",
            wire_api="chat_completions",
            reasoning_effort="low",
            start_date="2026-05-01",
            end_date="2026-05-07",
            reset_start_date="2026-05-01",
            reset_end_date="2026-05-02",
        )
        self.assertEqual({"task_id": "task-a-share", "message": "任务已创建，正在后台执行"}, response)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_start_a_share_analysis_preserves_missing_api_key_http_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import a_share_routes
        from backend.routes.a_share_routes import AShareAnalysisRunRequest

        request = AShareAnalysisRunRequest(group_id="51111112855254")

        with patch.object(
            a_share_routes,
            "create_a_share_analysis_task",
            side_effect=RuntimeError(a_share_routes.A_SHARE_MISSING_API_KEY_MESSAGE),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(a_share_routes.start_a_share_analysis(request, None))

        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual(a_share_routes.A_SHARE_MISSING_API_KEY_MESSAGE, raised.exception.detail)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_start_a_share_analysis_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import a_share_routes
        from backend.routes.a_share_routes import AShareAnalysisRunRequest

        with patch.object(a_share_routes, "create_a_share_analysis_task", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(a_share_routes.start_a_share_analysis(AShareAnalysisRunRequest(), None))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("创建A股分析任务失败: boom", raised.exception.detail)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_bounded_chart_top_n_clamps_to_existing_range(self):
        from backend.routes.a_share_routes import _bounded_chart_top_n

        self.assertEqual(1, _bounded_chart_top_n(0))
        self.assertEqual(20, _bounded_chart_top_n(20))
        self.assertEqual(100, _bounded_chart_top_n(999))

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_get_a_share_analysis_status_delegates_to_status_service(self):
        import asyncio

        from backend.routes import a_share_routes

        payload = {"summary": {"rows_count": 7}}

        with patch.object(a_share_routes, "get_a_share_analysis_status_payload", return_value=payload) as get_status:
            result = asyncio.run(a_share_routes.get_a_share_analysis_status(" 51111112855254 "))

        self.assertEqual(payload, result)
        get_status.assert_awaited_once_with(" 51111112855254 ")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_get_a_share_analysis_status_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import a_share_routes

        with patch.object(a_share_routes, "get_a_share_analysis_status_payload", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(a_share_routes.get_a_share_analysis_status("51111112855254"))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("获取A股分析状态失败: boom", raised.exception.detail)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_chart_payload_preserves_service_arguments(self):
        import asyncio

        from backend.routes import a_share_routes

        payload = {"chart_data": []}
        with patch.object(a_share_routes, "build_chart_payload", return_value=payload) as build_chart_payload:
            result = asyncio.run(
                a_share_routes._a_share_chart_payload(
                    "51111112855254",
                    "2026-05-01",
                    "2026-05-07",
                    999,
                )
            )

        self.assertEqual(payload, result)
        build_chart_payload.assert_called_once_with(
            start_date="2026-05-01",
            end_date="2026-05-07",
            top_n=100,
            ranking_windows=a_share_routes.A_SHARE_DEFAULT_RANKING_WINDOWS,
            group_id="51111112855254",
        )

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_reset_a_share_analysis_date_range_preserves_service_arguments(self):
        import asyncio

        from backend.routes import a_share_routes
        from backend.routes.a_share_routes import AShareAnalysisResetRangeRequest

        request = AShareAnalysisResetRangeRequest(
            group_id="51111112855254",
            start_date="2026-05-01",
            end_date="2026-05-07",
        )
        with patch.object(a_share_routes, "reset_analysis_range", return_value={"removed": 3}) as reset_range:
            result = asyncio.run(a_share_routes.reset_a_share_analysis_date_range(request))

        self.assertEqual({"success": True, "removed": 3}, result)
        reset_range.assert_called_once_with(
            "2026-05-01",
            "2026-05-07",
            group_id="51111112855254",
        )

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_export_tdx_delegates_to_workflow_launch(self):
        import asyncio

        from backend.routes import a_share_routes
        from backend.routes.a_share_routes import AShareAnalysisExportTdxRequest

        request = AShareAnalysisExportTdxRequest(
            group_id="51111112855254",
            group_name="纪要又要",
            start_date="2026-05-01",
            end_date="2026-05-07",
        )
        with patch.object(
            a_share_routes,
            "run_a_share_tdx_export",
            return_value={"success": True, "total_written": 2},
        ) as export_tdx:
            result = asyncio.run(a_share_routes.export_a_share_analysis_to_tdx(request))

        self.assertEqual({"success": True, "total_written": 2}, result)
        export_tdx.assert_awaited_once_with(
            group_id="51111112855254",
            group_name="纪要又要",
            start_date="2026-05-01",
            end_date="2026-05-07",
        )

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_success_payload_preserves_existing_merge_order(self):
        from backend.routes.a_share_routes import _success_payload

        self.assertEqual({"success": False, "count": 1}, _success_payload({"success": False, "count": 1}))


if __name__ == "__main__":
    unittest.main()
