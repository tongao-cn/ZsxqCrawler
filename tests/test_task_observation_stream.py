import asyncio
import json
import queue
import unittest


def _event_payload(event):
    return json.loads(event.removeprefix("data: ").strip())


class TaskObservationStreamTests(unittest.TestCase):
    def test_stream_replays_history_live_logs_status_and_terminal(self):
        from backend.services.task_observation_stream import (
            TaskObservationStreamDeps,
            stream_task_observation_events,
        )

        subscription = queue.Queue()
        subscription.put("live log")
        unsubscribed = []
        running_task = {"task_id": "task-1", "status": "running", "message": "处理中"}
        completed_task = {"task_id": "task-1", "status": "completed", "message": "完成"}
        task_states = iter([running_task, completed_task])
        deps = TaskObservationStreamDeps(
            subscribe_task_logs=lambda task_id: subscription,
            unsubscribe_task_logs=lambda task_id, active_subscription: unsubscribed.append(
                (task_id, active_subscription)
            ),
            get_task_logs_state=lambda task_id: ["old log"],
            get_task_state=lambda task_id: next(task_states),
            is_terminal_task_status=lambda status: status == "completed",
            log_wait_timeout_seconds=0.01,
        )

        async def collect_events():
            return [_event_payload(event) async for event in stream_task_observation_events("task-1", deps)]

        self.assertEqual(
            [
                {"type": "log", "message": "old log"},
                {"type": "status", "status": "running", "message": "处理中", "task": running_task},
                {"type": "log", "message": "live log"},
                {"type": "status", "status": "completed", "message": "完成", "task": completed_task},
            ],
            asyncio.run(collect_events()),
        )
        self.assertEqual([("task-1", subscription)], unsubscribed)

    def test_stream_emits_removed_event_when_task_disappears(self):
        from backend.services.task_observation_stream import (
            TaskObservationStreamDeps,
            stream_task_observation_events,
        )

        subscription = queue.Queue()
        unsubscribed = []
        deps = TaskObservationStreamDeps(
            subscribe_task_logs=lambda task_id: subscription,
            unsubscribe_task_logs=lambda task_id, active_subscription: unsubscribed.append(
                (task_id, active_subscription)
            ),
            get_task_logs_state=lambda task_id: None,
            get_task_state=lambda task_id: None,
            is_terminal_task_status=lambda status: False,
            log_wait_timeout_seconds=0.01,
        )

        async def collect_events():
            return [_event_payload(event) async for event in stream_task_observation_events("missing-task", deps)]

        self.assertEqual(
            [{"type": "status", "status": "cancelled", "message": "任务记录已被清理"}],
            asyncio.run(collect_events()),
        )
        self.assertEqual([("missing-task", subscription)], unsubscribed)


if __name__ == "__main__":
    unittest.main()
