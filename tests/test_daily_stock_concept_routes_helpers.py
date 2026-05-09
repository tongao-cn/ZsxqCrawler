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
