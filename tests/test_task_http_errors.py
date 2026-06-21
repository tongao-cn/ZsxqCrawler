import unittest
from importlib.util import find_spec


HAS_ROUTE_DEPS = find_spec("fastapi") is not None


class TaskHttpErrorsTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_route_error_preserves_http_exception_passthrough(self):
        from fastapi import HTTPException

        from backend.routes.task_http_errors import route_error

        original = HTTPException(status_code=404, detail="missing")

        self.assertIs(original, route_error("获取失败", original))

    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_route_error_maps_value_error_to_400(self):
        from backend.routes.task_http_errors import route_error

        error = route_error("创建任务失败", ValueError("stock_name 不能为空"))

        self.assertEqual(400, error.status_code)
        self.assertEqual("stock_name 不能为空", error.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_route_error_maps_ai_workflow_preflight_error(self):
        from backend.routes.task_http_errors import route_error
        from backend.services.ai_workflow_preflight import AIWorkflowPreflightError

        error = route_error("创建任务失败", AIWorkflowPreflightError(400, "missing key"))

        self.assertEqual(400, error.status_code)
        self.assertEqual("missing key", error.detail)

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

    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_task_launch_route_error_keeps_value_error_as_fallback_500(self):
        from backend.routes.task_http_errors import task_launch_route_error

        error = task_launch_route_error("创建任务失败", ValueError("bad workflow"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("创建任务失败: bad workflow", error.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "route dependencies are not installed")
    def test_task_launch_route_error_wraps_internal_http_exception_as_500(self):
        from fastapi import HTTPException

        from backend.routes.task_http_errors import task_launch_route_error

        original = HTTPException(status_code=409, detail="conflict")
        error = task_launch_route_error("创建任务失败", original)

        self.assertIsNot(original, error)
        self.assertEqual(500, error.status_code)
        self.assertEqual("创建任务失败: 409: conflict", error.detail)
