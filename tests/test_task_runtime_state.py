import queue
import threading
import unittest


class TaskRuntimeStateBundleTests(unittest.TestCase):
    def test_state_bundle_shares_runtime_containers_with_state(self):
        from backend.services.task_runtime_state import create_task_runtime_state_bundle

        bundle = create_task_runtime_state_bundle()

        bundle.state.initialize_task("task-1")
        self.assertEqual([], bundle.task_logs["task-1"])
        self.assertEqual(False, bundle.task_stop_flags["task-1"])

        bundle.current_tasks["task-1"] = {
            "task_id": "task-1",
            "status": "pending",
        }
        self.assertTrue(bundle.state.has_memory_task("task-1"))

        subscriber = queue.Queue()
        bundle.state.add_log_subscriber("task-1", subscriber)
        self.assertEqual([subscriber], bundle.sse_connections["task-1"])

        heartbeat = threading.Event()
        bundle.state.register_task_lock_heartbeat("task-1", heartbeat)
        self.assertIs(heartbeat, bundle.runtime_task_heartbeats["task-1"])

        thread = threading.Thread(target=lambda: None)
        bundle.state.register_runtime_task_thread("task-1", thread)
        self.assertIs(thread, bundle.runtime_task_threads["task-1"])


if __name__ == "__main__":
    unittest.main()
