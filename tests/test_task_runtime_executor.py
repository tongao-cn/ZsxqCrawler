import asyncio
import threading
import unittest


class TaskRuntimeExecutorTests(unittest.TestCase):
    def test_start_task_lock_heartbeat_skips_non_ingestion_task(self):
        from backend.services.task_runtime_executor import start_task_lock_heartbeat

        created_threads = []

        result = start_task_lock_heartbeat(
            "task-1",
            task={"task_id": "task-1"},
            ingestion_lock_key="ingestion",
            heartbeat_seconds=1,
            lease_minutes=30,
            register_heartbeat=lambda *_args: None,
            heartbeat_task_lock=lambda *_args: None,
            thread_factory=lambda **kwargs: created_threads.append(kwargs),
        )

        self.assertIsNone(result)
        self.assertEqual([], created_threads)

    def test_start_and_stop_task_lock_heartbeat_registers_event(self):
        from backend.services.task_runtime_executor import start_task_lock_heartbeat, stop_task_lock_heartbeat

        registered = {}
        created_threads = []

        class FakeThread:
            def __init__(self, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon
                self.started = False
                created_threads.append(self)

            def start(self):
                self.started = True

        event = start_task_lock_heartbeat(
            "task-1",
            task={"task_id": "task-1", "ingestion_lock_key": "ingestion"},
            ingestion_lock_key="ingestion",
            heartbeat_seconds=1,
            lease_minutes=30,
            register_heartbeat=lambda task_id, active_event: registered.setdefault(task_id, active_event),
            heartbeat_task_lock=lambda *_args: None,
            event_factory=threading.Event,
            thread_factory=FakeThread,
        )

        self.assertIs(event, registered["task-1"])
        self.assertEqual("zsxq-lock-heartbeat-task-1", created_threads[0].name)
        self.assertTrue(created_threads[0].daemon)
        self.assertTrue(created_threads[0].started)

        stop_task_lock_heartbeat("task-1", pop_heartbeat=lambda task_id: registered.pop(task_id, None))

        self.assertEqual({}, registered)
        self.assertTrue(event.is_set())

    def test_run_runtime_task_awaits_coroutine_and_forgets_thread(self):
        from backend.services.task_runtime_executor import run_runtime_task

        calls = []

        async def task_func(task_id, value):
            await asyncio.sleep(0)
            calls.append((task_id, value))

        run_runtime_task(
            task_func,
            "task-1",
            ("payload",),
            start_heartbeat=lambda task_id: calls.append(("start", task_id)),
            stop_heartbeat=lambda task_id: calls.append(("stop", task_id)),
            forget_thread=lambda task_id: calls.append(("forget", task_id)),
        )

        self.assertEqual(
            [("start", "task-1"), ("task-1", "payload"), ("stop", "task-1"), ("forget", "task-1")],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
