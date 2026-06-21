import json
import queue
import unittest
from datetime import datetime
from importlib.util import find_spec
from unittest.mock import patch


HAS_TASK_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class TaskRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_sse_event_formats_json_data_frame(self):
        from backend.routes.task_routes import _sse_event

        event = _sse_event({"type": "log", "message": "hello", "created_at": datetime(2026, 6, 21, 9, 30)})

        self.assertTrue(event.startswith("data: "))
        self.assertTrue(event.endswith("\n\n"))
        self.assertEqual(
            {"type": "log", "message": "hello", "created_at": "2026-06-21T09:30:00"},
            json.loads(event.removeprefix("data: ").strip()),
        )

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_status_payload_keeps_existing_fields(self):
        from backend.routes.task_routes import _task_status_payload

        task = {
            "task_id": "task-1",
            "type": "a_share_analysis",
            "status": "running",
            "message": "处理中",
            "display_name": "股票推荐池",
            "cancellable": False,
        }

        payload = _task_status_payload(task)

        self.assertEqual("status", payload["type"])
        self.assertEqual("running", payload["status"])
        self.assertEqual("处理中", payload["message"])
        self.assertEqual(task, payload["task"])

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_stream_payload_helpers_keep_existing_shapes(self):
        from backend.routes.task_routes import _task_heartbeat_payload, _task_log_payload, _task_removed_payload

        self.assertEqual({"type": "log", "message": "hello"}, _task_log_payload("hello"))
        self.assertEqual({"type": "heartbeat"}, _task_heartbeat_payload())
        self.assertEqual(
            {"type": "status", "status": "cancelled", "message": "任务记录已被清理"},
            _task_removed_payload(),
        )

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_streaming_response_headers_keep_sse_defaults(self):
        from backend.routes.task_routes import _streaming_response_headers

        self.assertEqual(
            {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
            _streaming_response_headers(),
        )

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_log_queue_helpers_wait_and_drain_messages(self):
        from backend.routes.task_routes import _drain_task_logs, _wait_for_task_log

        subscription = queue.Queue()
        subscription.put("first")
        subscription.put("second")

        self.assertEqual("first", _wait_for_task_log(subscription, timeout=0.01))
        self.assertEqual(["second"], _drain_task_logs(subscription))
        self.assertIsNone(_wait_for_task_log(subscription, timeout=0.01))

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_get_tasks_delegates_filtering_to_task_runtime(self):
        import asyncio

        from backend.routes import task_routes

        expected_tasks = [{"task_id": "task-1"}]

        with patch.object(task_routes, "list_tasks", return_value=expected_tasks) as list_tasks:
            result = asyncio.run(
                task_routes.get_tasks(limit=3, group_id=" 155 ", task_type="daily_analysis")
            )

        self.assertEqual(expected_tasks, result)
        list_tasks.assert_called_once_with(limit=3, group_id="155", task_type="daily_analysis")

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_get_tasks_omits_blank_group_filter(self):
        import asyncio

        from backend.routes import task_routes

        expected_tasks = [{"task_id": "task-1"}]

        with patch.object(task_routes, "list_tasks", return_value=expected_tasks) as list_tasks:
            result = asyncio.run(task_routes.get_tasks(limit=3, group_id=" ", task_type="daily_analysis"))

        self.assertEqual(expected_tasks, result)
        list_tasks.assert_called_once_with(limit=3, task_type="daily_analysis")


if __name__ == "__main__":
    unittest.main()
