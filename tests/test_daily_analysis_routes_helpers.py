import unittest
from importlib.util import find_spec
from unittest.mock import call, patch


HAS_DAILY_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


def fake_task(*args):
    return args


class DailyAnalysisRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_create_daily_task_response_creates_and_enqueues_task(self):
        from backend.routes.daily_analysis_routes import _create_daily_task_response

        background_tasks = FakeBackgroundTasks()
        metadata = {"group_id": "group-1", "report_date": "2026-05-07"}

        with (
            patch("backend.routes.daily_analysis_routes.create_task", return_value="task-1") as create_task,
            patch("backend.routes.daily_analysis_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_daily_task_response(
                background_tasks,
                "daily_topic_analysis",
                "生成每日话题 AI 报告 (群组: group-1)",
                metadata,
                fake_task,
                "group-1",
                "request",
            )

        create_task.assert_called_once_with(
            "daily_topic_analysis",
            "生成每日话题 AI 报告 (群组: group-1)",
            metadata,
        )
        self.assertEqual({"task_id": "task-1", "message": "任务已创建，正在后台执行"}, response)
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-1", "group-1", "request")
        self.assertEqual([], background_tasks.tasks)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_daily_task_metadata_preserves_group_and_report_date_fields(self):
        from backend.routes.daily_analysis_routes import _daily_task_metadata

        self.assertEqual(
            {"group_id": "group-1", "report_date": "2026-05-07"},
            _daily_task_metadata("group-1", "2026-05-07"),
        )
        self.assertEqual(
            {"group_id": "group-1", "report_date": None},
            _daily_task_metadata("group-1", None),
        )

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_build_daily_log_callback_writes_task_log(self):
        from backend.routes.daily_analysis_routes import _build_daily_log_callback

        log_callback = _build_daily_log_callback("task-1")

        with patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log:
            log_callback("hello")

        add_task_log.assert_called_once_with("task-1", "hello")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_analyze_daily_topics_for_task_preserves_service_arguments(self):
        from backend.routes.daily_analysis_routes import DailyAnalysisRequest, _analyze_daily_topics_for_task

        request = DailyAnalysisRequest(date="2026-06-13", commentsPerTopic=2)
        expected = {"report": []}
        with (
            patch("backend.routes.daily_analysis_routes.analyze_daily_topics", return_value=expected) as analyze,
            patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log,
        ):
            result = _analyze_daily_topics_for_task("task-1", "51111112855254", request)

            self.assertEqual(expected, result)
            analyze.assert_called_once()
            call_args, call_kwargs = analyze.call_args
            self.assertEqual(("51111112855254", "2026-06-13"), call_args)
            self.assertEqual(2, call_kwargs["comments_per_topic"])

            call_kwargs["log_callback"]("daily log")

        add_task_log.assert_called_once_with("task-1", "daily log")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_run_daily_analysis_task_uses_runtime_workflow_lifecycle(self):
        from backend.routes.daily_analysis_routes import DailyAnalysisRequest, run_daily_analysis_task

        request = DailyAnalysisRequest(date="2026-06-13", commentsPerTopic=2)
        with (
            patch("backend.routes.daily_analysis_routes.run_workflow") as run_workflow,
            patch("backend.routes.daily_analysis_routes.analyze_daily_topics", return_value={"report": []}) as analyze,
        ):
            run_daily_analysis_task("task-1", "51111112855254", request)

            run_workflow.assert_called_once()
            args, kwargs = run_workflow.call_args
            self.assertEqual(("task-1",), args)
            self.assertEqual("开始生成每日话题 AI 报告...", kwargs["running_message"])
            self.assertEqual("每日话题 AI 报告生成完成", kwargs["completed_message"])
            self.assertEqual("每日话题 AI 报告生成", kwargs["failure_label"])

            result = kwargs["work"]()
            self.assertEqual({"report": []}, result)
            analyze.assert_called_once()
            call_args, call_kwargs = analyze.call_args
            self.assertEqual(("51111112855254", "2026-06-13"), call_args)
            self.assertEqual(2, call_kwargs["comments_per_topic"])
            self.assertTrue(callable(call_kwargs["log_callback"]))

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_daily_task_stopped_or_failed_checks_stop_before_status(self):
        from backend.routes import daily_analysis_routes

        with patch.object(daily_analysis_routes, "is_task_stopped", return_value=True) as is_task_stopped:
            stopped = daily_analysis_routes._daily_task_stopped_or_failed("task-1")

        is_task_stopped.assert_called_once_with("task-1")
        self.assertTrue(stopped)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_daily_task_stopped_or_failed_detects_failed_status(self):
        from backend.routes import daily_analysis_routes

        with (
            patch.object(daily_analysis_routes, "is_task_stopped", return_value=False),
            patch.dict(daily_analysis_routes.current_tasks, {"task-1": {"status": "failed"}}, clear=True),
        ):
            failed = daily_analysis_routes._daily_task_stopped_or_failed("task-1")

        self.assertTrue(failed)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_fail_daily_task_unless_stopped_logs_and_updates_failure(self):
        from backend.routes.daily_analysis_routes import _fail_daily_task_unless_stopped

        with (
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=False),
            patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log,
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
        ):
            _fail_daily_task_unless_stopped("task-1", "每日话题 AI 报告生成", RuntimeError("boom"))

        add_task_log.assert_called_once_with("task-1", "❌ 每日话题 AI 报告生成失败: boom")
        update_task.assert_called_once_with("task-1", "failed", "每日话题 AI 报告生成失败: boom")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_fail_daily_task_unless_stopped_skips_stopped_task(self):
        from backend.routes.daily_analysis_routes import _fail_daily_task_unless_stopped

        with (
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=True),
            patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log,
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
        ):
            _fail_daily_task_unless_stopped("task-1", "每日抓取与 AI 分析", RuntimeError("boom"))

        add_task_log.assert_not_called()
        update_task.assert_not_called()

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_run_daily_today_task_preserves_crawl_first_lifecycle(self):
        from backend.routes.daily_analysis_routes import DailyRunTodayRequest, run_daily_today_task

        request = DailyRunTodayRequest(date="2026-06-13", commentsPerTopic=2, crawlLatestFirst=True)
        result = {"report": []}

        with (
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
            patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log,
            patch("backend.routes.daily_analysis_routes.run_crawl_latest_task") as run_crawl_latest_task,
            patch("backend.routes.daily_analysis_routes._daily_task_stopped_or_failed", return_value=False)
            as stopped_or_failed,
            patch("backend.routes.daily_analysis_routes._analyze_daily_topics_for_task", return_value=result)
            as analyze,
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=False) as is_task_stopped,
        ):
            run_daily_today_task("task-1", "group-1", request)

        self.assertEqual(
            [
                call("task-1", "running", "开始每日抓取与 AI 分析..."),
                call("task-1", "running", "最新话题抓取完成，开始 AI 分析..."),
                call("task-1", "completed", "每日抓取与 AI 分析完成", result),
            ],
            update_task.call_args_list,
        )
        add_task_log.assert_called_once_with("task-1", "🔄 先抓取最新话题...")
        run_crawl_latest_task.assert_called_once_with("task-1", "group-1", None)
        stopped_or_failed.assert_called_once_with("task-1")
        analyze.assert_called_once_with("task-1", "group-1", request)
        is_task_stopped.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_run_daily_today_task_returns_after_crawl_stop_or_failure(self):
        from backend.routes.daily_analysis_routes import DailyRunTodayRequest, run_daily_today_task

        request = DailyRunTodayRequest(date="2026-06-13", crawlLatestFirst=True)

        with (
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
            patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log,
            patch("backend.routes.daily_analysis_routes.run_crawl_latest_task") as run_crawl_latest_task,
            patch("backend.routes.daily_analysis_routes._daily_task_stopped_or_failed", return_value=True)
            as stopped_or_failed,
            patch("backend.routes.daily_analysis_routes._analyze_daily_topics_for_task") as analyze,
            patch("backend.routes.daily_analysis_routes.is_task_stopped") as is_task_stopped,
        ):
            run_daily_today_task("task-1", "group-1", request)

        update_task.assert_called_once_with("task-1", "running", "开始每日抓取与 AI 分析...")
        add_task_log.assert_called_once_with("task-1", "🔄 先抓取最新话题...")
        run_crawl_latest_task.assert_called_once_with("task-1", "group-1", None)
        stopped_or_failed.assert_called_once_with("task-1")
        analyze.assert_not_called()
        is_task_stopped.assert_not_called()

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_run_daily_today_task_skips_crawl_when_disabled(self):
        from backend.routes.daily_analysis_routes import DailyRunTodayRequest, run_daily_today_task

        request = DailyRunTodayRequest(date="2026-06-13", commentsPerTopic=2, crawlLatestFirst=False)
        result = {"report": []}

        with (
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
            patch("backend.routes.daily_analysis_routes.add_task_log") as add_task_log,
            patch("backend.routes.daily_analysis_routes.run_crawl_latest_task") as run_crawl_latest_task,
            patch("backend.routes.daily_analysis_routes._daily_task_stopped_or_failed") as stopped_or_failed,
            patch("backend.routes.daily_analysis_routes._analyze_daily_topics_for_task", return_value=result)
            as analyze,
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=False) as is_task_stopped,
        ):
            run_daily_today_task("task-1", "group-1", request)

        self.assertEqual(
            [
                call("task-1", "running", "开始每日抓取与 AI 分析..."),
                call("task-1", "completed", "每日抓取与 AI 分析完成", result),
            ],
            update_task.call_args_list,
        )
        add_task_log.assert_not_called()
        run_crawl_latest_task.assert_not_called()
        stopped_or_failed.assert_not_called()
        analyze.assert_called_once_with("task-1", "group-1", request)
        is_task_stopped.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_run_daily_today_task_returns_when_stopped_after_analysis(self):
        from backend.routes.daily_analysis_routes import DailyRunTodayRequest, run_daily_today_task

        request = DailyRunTodayRequest(date="2026-06-13", crawlLatestFirst=False)

        with (
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
            patch("backend.routes.daily_analysis_routes._run_daily_today_crawl_first_step", return_value=True)
            as crawl_first_step,
            patch("backend.routes.daily_analysis_routes._analyze_daily_topics_for_task", return_value={"report": []})
            as analyze,
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=True) as is_task_stopped,
        ):
            run_daily_today_task("task-1", "group-1", request)

        update_task.assert_called_once_with("task-1", "running", "开始每日抓取与 AI 分析...")
        crawl_first_step.assert_called_once_with("task-1", "group-1", request)
        analyze.assert_called_once_with("task-1", "group-1", request)
        is_task_stopped.assert_called_once_with("task-1")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_complete_daily_today_task_unless_stopped_preserves_completed_result(self):
        from backend.routes.daily_analysis_routes import _complete_daily_today_task_unless_stopped

        result = {"report": []}
        with (
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=False) as is_task_stopped,
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
        ):
            _complete_daily_today_task_unless_stopped("task-1", result)

        is_task_stopped.assert_called_once_with("task-1")
        update_task.assert_called_once_with("task-1", "completed", "每日抓取与 AI 分析完成", result)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_complete_daily_today_task_unless_stopped_skips_stopped_task(self):
        from backend.routes.daily_analysis_routes import _complete_daily_today_task_unless_stopped

        with (
            patch("backend.routes.daily_analysis_routes.is_task_stopped", return_value=True) as is_task_stopped,
            patch("backend.routes.daily_analysis_routes.update_task") as update_task,
        ):
            _complete_daily_today_task_unless_stopped("task-1", {"report": []})

        is_task_stopped.assert_called_once_with("task-1")
        update_task.assert_not_called()

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_read_daily_report_preserves_report_passthrough(self):
        import asyncio

        from backend.routes import daily_analysis_routes

        report = {"date": "2026-06-13", "topics": []}
        with patch.object(daily_analysis_routes, "get_daily_report", return_value=report) as get_report:
            result = asyncio.run(daily_analysis_routes.read_daily_report("group-1", "2026-06-13"))

        self.assertEqual(report, result)
        get_report.assert_called_once_with("group-1", "2026-06-13")

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_read_daily_report_preserves_missing_report_404(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import daily_analysis_routes

        with patch.object(daily_analysis_routes, "get_daily_report", return_value=None) as get_report:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(daily_analysis_routes.read_daily_report("group-1", None))

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("日报不存在，请先生成", raised.exception.detail)
        get_report.assert_called_once_with("group-1", None)

    @unittest.skipUnless(HAS_DAILY_ROUTE_DEPS, "daily analysis route dependencies are not installed")
    def test_daily_report_or_404_preserves_missing_report_404(self):
        from fastapi import HTTPException

        from backend.routes import daily_analysis_routes

        with patch.object(daily_analysis_routes, "get_daily_report", return_value={}) as get_report:
            with self.assertRaises(HTTPException) as raised:
                daily_analysis_routes._daily_report_or_404("group-1", "2026-06-13")

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("日报不存在，请先生成", raised.exception.detail)
        get_report.assert_called_once_with("group-1", "2026-06-13")


if __name__ == "__main__":
    unittest.main()
