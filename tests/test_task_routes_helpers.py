import json
import queue
import unittest
from datetime import datetime
from importlib.util import find_spec
from unittest.mock import patch


HAS_TASK_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class TaskRoutesHelperTests(unittest.TestCase):
    def _event_payload(self, event):
        return json.loads(event.removeprefix("data: ").strip())

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_status_event_formats_json_data_frame(self):
        from backend.routes.task_stream_events import task_status_event

        task = {
            "task_id": "task-1",
            "status": "running",
            "message": "处理中",
            "created_at": datetime(2026, 6, 21, 9, 30),
        }
        event = task_status_event(task)

        self.assertTrue(event.startswith("data: "))
        self.assertTrue(event.endswith("\n\n"))
        self.assertEqual(
            {
                "type": "status",
                "status": "running",
                "message": "处理中",
                "task": {
                    "task_id": "task-1",
                    "status": "running",
                    "message": "处理中",
                    "created_at": "2026-06-21T09:30:00",
                },
            },
            self._event_payload(event),
        )

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_status_event_keeps_existing_fields(self):
        from backend.routes.task_stream_events import task_status_event

        task = {
            "task_id": "task-1",
            "type": "a_share_analysis",
            "status": "running",
            "message": "处理中",
            "display_name": "股票推荐池",
            "cancellable": False,
        }

        payload = self._event_payload(task_status_event(task))

        self.assertEqual("status", payload["type"])
        self.assertEqual("running", payload["status"])
        self.assertEqual("处理中", payload["message"])
        self.assertEqual(task, payload["task"])

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_stream_events_keep_existing_shapes(self):
        from backend.routes.task_stream_events import task_heartbeat_event, task_log_event, task_removed_event

        self.assertEqual({"type": "log", "message": "hello"}, self._event_payload(task_log_event("hello")))
        self.assertEqual({"type": "heartbeat"}, self._event_payload(task_heartbeat_event()))
        self.assertEqual(
            {"type": "status", "status": "cancelled", "message": "任务记录已被清理"},
            self._event_payload(task_removed_event()),
        )

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_streaming_response_headers_keep_sse_defaults(self):
        from backend.routes.task_stream_events import streaming_response_headers

        self.assertEqual(
            {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            },
            streaming_response_headers(),
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
    def test_task_stream_emits_logs_status_and_terminal_without_heartbeat_after_terminal(self):
        import asyncio

        from backend.routes import task_routes

        subscription = queue.Queue()
        subscription.put("live log")
        running_task = {"task_id": "task-1", "status": "running", "message": "处理中"}
        completed_task = {"task_id": "task-1", "status": "completed", "message": "完成"}

        async def collect_events():
            response = await task_routes.stream_task_logs("task-1")
            return [self._event_payload(event) async for event in response.body_iterator]

        with (
            patch.object(task_routes, "subscribe_task_logs", return_value=subscription) as subscribe,
            patch.object(task_routes, "unsubscribe_task_logs") as unsubscribe,
            patch.object(task_routes, "get_task_logs_state", return_value=["old log"]),
            patch.object(task_routes, "get_task_state", side_effect=[running_task, completed_task]),
        ):
            payloads = asyncio.run(collect_events())

        self.assertEqual(
            [
                {"type": "log", "message": "old log"},
                {"type": "status", "status": "running", "message": "处理中", "task": running_task},
                {"type": "log", "message": "live log"},
                {"type": "status", "status": "completed", "message": "完成", "task": completed_task},
            ],
            payloads,
        )
        subscribe.assert_called_once_with("task-1")
        unsubscribe.assert_called_once_with("task-1", subscription)

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
