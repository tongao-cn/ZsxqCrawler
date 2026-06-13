import unittest
from importlib.util import find_spec
from unittest.mock import patch


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


if __name__ == "__main__":
    unittest.main()
