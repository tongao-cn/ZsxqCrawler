import json
import queue
import unittest
from importlib.util import find_spec


HAS_TASK_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class TaskRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_sse_event_formats_json_data_frame(self):
        from backend.routes.task_routes import _sse_event

        event = _sse_event({"type": "log", "message": "hello"})

        self.assertTrue(event.startswith("data: "))
        self.assertTrue(event.endswith("\n\n"))
        self.assertEqual({"type": "log", "message": "hello"}, json.loads(event.removeprefix("data: ").strip()))

    @unittest.skipUnless(HAS_TASK_ROUTE_DEPS, "task route dependencies are not installed")
    def test_task_status_payload_keeps_existing_fields(self):
        from backend.routes.task_routes import _task_status_payload

        payload = _task_status_payload({"status": "running", "message": "处理中", "extra": "ignored"})

        self.assertEqual({"type": "status", "status": "running", "message": "处理中"}, payload)

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


if __name__ == "__main__":
    unittest.main()
