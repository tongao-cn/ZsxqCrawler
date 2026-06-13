import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


class DailyStockConceptRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_stock_concept_task_metadata_preserves_fields(self):
        from backend.routes.daily_stock_concept_routes import _stock_concept_task_metadata

        self.assertEqual(
            {"group_id": "51111112855254", "report_date": "2026-06-13"},
            _stock_concept_task_metadata("51111112855254", "2026-06-13"),
        )
        self.assertEqual(
            {"group_id": "51111112855254", "report_date": None},
            _stock_concept_task_metadata("51111112855254", None),
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_create_daily_stock_concept_task_response_preserves_task_contract(self):
        from backend.routes.daily_stock_concept_routes import (
            TASK_CREATED_MESSAGE,
            DailyStockConceptRequest,
            _create_daily_stock_concept_task_response,
            run_daily_stock_concept_task,
        )

        request = DailyStockConceptRequest(date="2026-06-13", commentsPerTopic=3)

        with (
            patch("backend.routes.daily_stock_concept_routes.create_task", return_value="task-concept") as create_task,
            patch("backend.routes.daily_stock_concept_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_daily_stock_concept_task_response("51111112855254", request)

        create_task.assert_called_once_with(
            "daily_stock_concepts",
            "提取每日股票概念 (群组: 51111112855254)",
            {"group_id": "51111112855254", "report_date": "2026-06-13"},
        )
        enqueue_runtime_task.assert_called_once_with(
            run_daily_stock_concept_task,
            "task-concept",
            "51111112855254",
            request,
        )
        self.assertEqual({"task_id": "task-concept", "message": TASK_CREATED_MESSAGE}, response)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_build_stock_concept_log_callback_writes_task_log(self):
        from backend.routes.daily_stock_concept_routes import _build_stock_concept_log_callback

        log_callback = _build_stock_concept_log_callback("task-1")

        with patch("backend.routes.daily_stock_concept_routes.add_task_log") as add_task_log:
            log_callback("hello")

        add_task_log.assert_called_once_with("task-1", "hello")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_fail_stock_concept_task_unless_stopped_logs_and_updates_failure(self):
        from backend.routes.daily_stock_concept_routes import _fail_stock_concept_task_unless_stopped

        with (
            patch("backend.routes.daily_stock_concept_routes.is_task_stopped", return_value=False),
            patch("backend.routes.daily_stock_concept_routes.add_task_log") as add_task_log,
            patch("backend.routes.daily_stock_concept_routes.update_task") as update_task,
        ):
            _fail_stock_concept_task_unless_stopped("task-1", RuntimeError("boom"))

        add_task_log.assert_called_once_with("task-1", "❌ 每日股票概念提取失败: boom")
        update_task.assert_called_once_with("task-1", "failed", "每日股票概念提取失败: boom")


if __name__ == "__main__":
    unittest.main()
