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
    def test_start_a_share_analysis_preserves_missing_api_key_http_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes.a_share_routes import AShareAnalysisRunRequest, start_a_share_analysis

        request = AShareAnalysisRunRequest(group_id="51111112855254")
        missing_key_message = "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"

        with (
            patch("backend.routes.a_share_routes.has_openai_api_key", return_value=False) as has_api_key,
            patch("backend.routes.a_share_routes._normalize_group_scope") as normalize_group_scope,
            patch("backend.routes.a_share_routes._create_a_share_analysis_task_response") as create_task_response,
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(start_a_share_analysis(request, None))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual(f"创建A股分析任务失败: 400: {missing_key_message}", raised.exception.detail)
        has_api_key.assert_called_once_with()
        normalize_group_scope.assert_not_called()
        create_task_response.assert_not_called()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_get_a_share_analysis_status_preserves_storage_failure_fallback(self):
        import asyncio

        from backend.routes import a_share_routes

        summary = {"rows_count": 7, "processed_items": 5}
        latest_task = {"id": "latest"}
        running_task = {"id": "running"}
        latest_export = {"block_name": "A-share"}

        def latest_task_side_effect(task_type, status=None, group_id=None):
            self.assertEqual("a_share_analysis", task_type)
            self.assertEqual("51111112855254", group_id)
            return running_task if status == "running" else latest_task

        with (
            patch.object(a_share_routes, "get_analysis_summary", return_value=summary) as get_summary,
            patch.object(a_share_routes, "get_latest_task_by_type", side_effect=latest_task_side_effect)
            as get_latest_task,
            patch.object(a_share_routes, "get_storage_health", side_effect=RuntimeError("temporary outage"))
            as get_storage_health,
            patch.object(a_share_routes, "get_latest_tdx_export", return_value=latest_export) as get_latest_export,
            patch.object(a_share_routes, "has_openai_api_key", return_value=True) as has_api_key,
        ):
            result = asyncio.run(a_share_routes.get_a_share_analysis_status(" 51111112855254 "))

        self.assertEqual(summary, result["summary"])
        self.assertEqual("51111112855254", result["group_id"])
        self.assertEqual(latest_task, result["latest_task"])
        self.assertEqual(running_task, result["running_task"])
        self.assertEqual(
            {
                "enabled": False,
                "mode": "file_fallback",
                "label": "本地文件降级（PostgreSQL 不可用: temporary outage）",
                "daily_rows": 7,
                "processed_rows": 5,
            },
            result["storage"],
        )
        self.assertEqual(latest_export, result["latest_tdx_export"])
        self.assertTrue(result["api_key_configured"])
        get_summary.assert_called_once_with(group_id="51111112855254")
        self.assertEqual(2, get_latest_task.call_count)
        get_storage_health.assert_called_once_with(group_id="51111112855254")
        get_latest_export.assert_called_once_with("51111112855254")
        has_api_key.assert_called_once_with()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_get_a_share_analysis_status_preserves_latest_tdx_export_failure_fallback(self):
        import asyncio

        from backend.routes import a_share_routes

        summary = {"rows_count": 7, "processed_items": 5}
        storage = {"enabled": True, "mode": "postgres"}

        with (
            patch.object(a_share_routes, "get_analysis_summary", return_value=summary) as get_summary,
            patch.object(a_share_routes, "get_latest_task_by_type", return_value=None) as get_latest_task,
            patch.object(a_share_routes, "_a_share_storage_status", return_value=storage) as get_storage_status,
            patch.object(a_share_routes, "get_latest_tdx_export", side_effect=RuntimeError("tdx unavailable"))
            as get_latest_export,
            patch.object(a_share_routes, "has_openai_api_key", return_value=False) as has_api_key,
        ):
            result = asyncio.run(a_share_routes.get_a_share_analysis_status("51111112855254"))

        self.assertEqual(summary, result["summary"])
        self.assertEqual("51111112855254", result["group_id"])
        self.assertIsNone(result["latest_task"])
        self.assertIsNone(result["running_task"])
        self.assertEqual(storage, result["storage"])
        self.assertIsNone(result["latest_tdx_export"])
        self.assertFalse(result["api_key_configured"])
        get_summary.assert_called_once_with(group_id="51111112855254")
        self.assertEqual(2, get_latest_task.call_count)
        get_storage_status.assert_awaited_once_with(summary, "51111112855254")
        get_latest_export.assert_called_once_with("51111112855254")
        has_api_key.assert_called_once_with()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_status_tasks_preserves_latest_then_running_lookup_order(self):
        import asyncio

        from backend.routes import a_share_routes

        summary = {"rows_count": 7}
        storage = {"enabled": True, "mode": "postgres"}
        latest_export = {"block_name": "A-share"}
        latest_task = {"id": "latest"}
        running_task = {"id": "running"}
        events = []

        def latest_task_side_effect(*args, **kwargs):
            events.append((args, kwargs))
            return latest_task if len(events) == 1 else running_task

        with (
            patch.object(a_share_routes, "get_analysis_summary", return_value=summary),
            patch.object(
                a_share_routes,
                "get_latest_task_by_type",
                side_effect=latest_task_side_effect,
            ) as get_latest_task,
            patch.object(a_share_routes, "_a_share_storage_status", return_value=storage),
            patch.object(a_share_routes, "_latest_a_share_tdx_export", return_value=latest_export),
            patch.object(a_share_routes, "has_openai_api_key", return_value=True),
        ):
            result = asyncio.run(a_share_routes.get_a_share_analysis_status("51111112855254"))

        self.assertEqual(latest_task, result["latest_task"])
        self.assertEqual(running_task, result["running_task"])
        self.assertEqual(
            [
                (("a_share_analysis",), {"group_id": "51111112855254"}),
                (("a_share_analysis",), {"status": "running", "group_id": "51111112855254"}),
            ],
            events,
        )
        self.assertEqual(2, get_latest_task.call_count)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_status_tasks_returns_latest_and_running_tasks(self):
        from backend.routes import a_share_routes

        latest_task = {"id": "latest"}
        running_task = {"id": "running"}

        with patch.object(
            a_share_routes,
            "get_latest_task_by_type",
            side_effect=[latest_task, running_task],
        ) as get_latest_task:
            self.assertEqual(
                (latest_task, running_task),
                a_share_routes._a_share_status_tasks("51111112855254"),
            )

        get_latest_task.assert_any_call("a_share_analysis", group_id="51111112855254")
        get_latest_task.assert_any_call("a_share_analysis", status="running", group_id="51111112855254")
        self.assertEqual(2, get_latest_task.call_count)

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_file_fallback_storage_status_defaults_missing_counts(self):
        from backend.routes.a_share_routes import _a_share_file_fallback_storage_status

        self.assertEqual(
            {
                "enabled": False,
                "mode": "file_fallback",
                "label": "本地文件降级（PostgreSQL 不可用: temporary outage）",
                "daily_rows": 0,
                "processed_rows": 0,
            },
            _a_share_file_fallback_storage_status(
                {"rows_count": None},
                RuntimeError("temporary outage"),
            ),
        )

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_latest_a_share_tdx_export_returns_service_payload(self):
        import asyncio

        from backend.routes import a_share_routes

        payload = {"block_name": "A-share"}
        with patch.object(a_share_routes, "get_latest_tdx_export", return_value=payload) as get_latest_export:
            result = asyncio.run(a_share_routes._latest_a_share_tdx_export("51111112855254"))

        self.assertEqual(payload, result)
        get_latest_export.assert_called_once_with("51111112855254")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_latest_a_share_tdx_export_returns_none_on_failure(self):
        import asyncio

        from backend.routes import a_share_routes

        with patch.object(
            a_share_routes,
            "get_latest_tdx_export",
            side_effect=RuntimeError("tdx unavailable"),
        ) as get_latest_export:
            result = asyncio.run(a_share_routes._latest_a_share_tdx_export("51111112855254"))

        self.assertIsNone(result)
        get_latest_export.assert_called_once_with("51111112855254")

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
    def test_fail_a_share_analysis_task_preserves_failure_status_and_log(self):
        from backend.routes.a_share_routes import _fail_a_share_analysis_task

        with (
            patch("backend.routes.a_share_routes.add_task_log") as add_task_log,
            patch("backend.routes.a_share_routes.update_task") as update_task,
        ):
            _fail_a_share_analysis_task("task-a-share", RuntimeError("boom"))

        add_task_log.assert_called_once_with("task-a-share", "❌ A股公司分析失败: boom")
        update_task.assert_called_once_with("task-a-share", "failed", "A股公司分析失败: boom")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_fail_a_share_analysis_task_swallows_failure_recording_errors(self):
        from backend.routes.a_share_routes import _fail_a_share_analysis_task

        with (
            patch("backend.routes.a_share_routes.add_task_log", side_effect=RuntimeError("log failed")) as add_task_log,
            patch("backend.routes.a_share_routes.update_task") as update_task,
        ):
            _fail_a_share_analysis_task("task-a-share", RuntimeError("boom"))

        add_task_log.assert_called_once_with("task-a-share", "❌ A股公司分析失败: boom")
        update_task.assert_not_called()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_complete_a_share_analysis_task_preserves_status_result_and_log(self):
        from backend.routes.a_share_routes import _complete_a_share_analysis_task

        result = {"processed": 3}
        with (
            patch("backend.routes.a_share_routes.update_task") as update_task,
            patch("backend.routes.a_share_routes.add_task_log") as add_task_log,
        ):
            _complete_a_share_analysis_task("task-a-share", result)

        update_task.assert_called_once_with("task-a-share", "completed", "A股公司分析完成", result)
        add_task_log.assert_called_once_with("task-a-share", "✅ A股公司分析完成")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_run_a_share_analysis_task_fails_fast_without_api_key(self):
        from backend.routes.a_share_routes import AShareAnalysisRunRequest, run_a_share_analysis_task

        events = []

        def update_task_side_effect(*args):
            events.append(("update_task", args))

        def add_task_log_side_effect(*args):
            events.append(("add_task_log", args))

        request = AShareAnalysisRunRequest(group_id="51111112855254")
        message = "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"

        with (
            patch("backend.routes.a_share_routes.has_openai_api_key", return_value=False),
            patch("backend.routes.a_share_routes.update_task", side_effect=update_task_side_effect) as update_task,
            patch("backend.routes.a_share_routes.add_task_log", side_effect=add_task_log_side_effect) as add_task_log,
            patch("backend.routes.a_share_routes.is_task_stopped") as is_task_stopped,
            patch("backend.routes.a_share_routes._start_a_share_analysis_task") as start_task,
            patch("backend.routes.a_share_routes._run_a_share_analysis_for_task") as run_analysis,
            patch("backend.routes.a_share_routes._complete_a_share_analysis_task") as complete_task,
        ):
            run_a_share_analysis_task("task-a-share", request)

        self.assertEqual(
            [
                ("update_task", ("task-a-share", "failed", message)),
                ("add_task_log", ("task-a-share", f"❌ {message}")),
            ],
            events,
        )
        update_task.assert_called_once_with("task-a-share", "failed", message)
        add_task_log.assert_called_once_with("task-a-share", f"❌ {message}")
        is_task_stopped.assert_not_called()
        start_task.assert_not_called()
        run_analysis.assert_not_called()
        complete_task.assert_not_called()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_api_key_available_or_fail_task_returns_true_when_configured(self):
        from backend.routes.a_share_routes import _a_share_api_key_available_or_fail_task

        with (
            patch("backend.routes.a_share_routes.has_openai_api_key", return_value=True) as has_api_key,
            patch("backend.routes.a_share_routes.update_task") as update_task,
            patch("backend.routes.a_share_routes.add_task_log") as add_task_log,
        ):
            available = _a_share_api_key_available_or_fail_task("task-a-share")

        self.assertTrue(available)
        has_api_key.assert_called_once_with()
        update_task.assert_not_called()
        add_task_log.assert_not_called()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_api_key_available_or_fail_task_records_missing_key_failure(self):
        from backend.routes.a_share_routes import _a_share_api_key_available_or_fail_task

        events = []

        def update_task_side_effect(*args):
            events.append(("update_task", args))

        def add_task_log_side_effect(*args):
            events.append(("add_task_log", args))

        message = "未配置 OpenAI API Key，请设置环境变量 OPENAI_API_KEY 或 config.toml [ai].api_key"
        with (
            patch("backend.routes.a_share_routes.has_openai_api_key", return_value=False) as has_api_key,
            patch("backend.routes.a_share_routes.update_task", side_effect=update_task_side_effect) as update_task,
            patch("backend.routes.a_share_routes.add_task_log", side_effect=add_task_log_side_effect) as add_task_log,
        ):
            available = _a_share_api_key_available_or_fail_task("task-a-share")

        self.assertFalse(available)
        has_api_key.assert_called_once_with()
        self.assertEqual(
            [
                ("update_task", ("task-a-share", "failed", message)),
                ("add_task_log", ("task-a-share", f"❌ {message}")),
            ],
            events,
        )
        update_task.assert_called_once_with("task-a-share", "failed", message)
        add_task_log.assert_called_once_with("task-a-share", f"❌ {message}")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_run_a_share_analysis_task_returns_when_stopped_before_run(self):
        from backend.routes.a_share_routes import AShareAnalysisRunRequest, run_a_share_analysis_task

        request = AShareAnalysisRunRequest(group_id="51111112855254")
        with (
            patch("backend.routes.a_share_routes._a_share_api_key_available_or_fail_task", return_value=True)
            as api_key_preflight,
            patch("backend.routes.a_share_routes.is_task_stopped", return_value=True) as is_task_stopped,
            patch("backend.routes.a_share_routes._normalize_group_scope") as normalize_group_scope,
            patch("backend.routes.a_share_routes._start_a_share_analysis_task") as start_task,
            patch("backend.routes.a_share_routes._run_a_share_analysis_for_task") as run_analysis,
            patch("backend.routes.a_share_routes._complete_a_share_analysis_task") as complete_task,
        ):
            run_a_share_analysis_task("task-a-share", request)

        api_key_preflight.assert_called_once_with("task-a-share")
        is_task_stopped.assert_called_once_with("task-a-share")
        normalize_group_scope.assert_not_called()
        start_task.assert_not_called()
        run_analysis.assert_not_called()
        complete_task.assert_not_called()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_task_ready_to_start_skips_stop_check_when_api_key_missing(self):
        from backend.routes.a_share_routes import _a_share_task_ready_to_start

        with (
            patch("backend.routes.a_share_routes._a_share_api_key_available_or_fail_task", return_value=False)
            as api_key_preflight,
            patch("backend.routes.a_share_routes.is_task_stopped") as is_task_stopped,
        ):
            ready = _a_share_task_ready_to_start("task-a-share")

        self.assertFalse(ready)
        api_key_preflight.assert_called_once_with("task-a-share")
        is_task_stopped.assert_not_called()

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_task_ready_to_start_returns_false_when_stopped(self):
        from backend.routes.a_share_routes import _a_share_task_ready_to_start

        with (
            patch("backend.routes.a_share_routes._a_share_api_key_available_or_fail_task", return_value=True)
            as api_key_preflight,
            patch("backend.routes.a_share_routes.is_task_stopped", return_value=True) as is_task_stopped,
        ):
            ready = _a_share_task_ready_to_start("task-a-share")

        self.assertFalse(ready)
        api_key_preflight.assert_called_once_with("task-a-share")
        is_task_stopped.assert_called_once_with("task-a-share")

    @unittest.skipUnless(HAS_A_SHARE_ROUTE_DEPS, "a-share route dependencies are not installed")
    def test_a_share_task_ready_to_start_returns_true_when_not_stopped(self):
        from backend.routes.a_share_routes import _a_share_task_ready_to_start

        with (
            patch("backend.routes.a_share_routes._a_share_api_key_available_or_fail_task", return_value=True)
            as api_key_preflight,
            patch("backend.routes.a_share_routes.is_task_stopped", return_value=False) as is_task_stopped,
        ):
            ready = _a_share_task_ready_to_start("task-a-share")

        self.assertTrue(ready)
        api_key_preflight.assert_called_once_with("task-a-share")
        is_task_stopped.assert_called_once_with("task-a-share")

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
