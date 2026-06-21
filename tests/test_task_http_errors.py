import unittest
from importlib.util import find_spec


HAS_ROUTE_DEPS = find_spec("fastapi") is not None


class TaskHttpErrorsTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_task_launch_route_error_maps_ingestion_conflict_to_409(self):
        from backend.routes.task_http_errors import task_launch_route_error
        from backend.services.task_launch import TaskLaunchConflict

        error = task_launch_route_error(
            "创建任务失败",
            TaskLaunchConflict({"task_id": "task-old", "type": "crawl_all", "status": "running"}),
        )

        self.assertEqual(409, error.status_code)
        self.assertEqual(
            {
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-old",
                "type": "crawl_all",
                "status": "running",
            },
            error.detail,
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_task_launch_route_error_formats_unexpected_error_as_500(self):
        from backend.routes.task_http_errors import task_launch_route_error

        error = task_launch_route_error("创建任务失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("创建任务失败: boom", error.detail)
