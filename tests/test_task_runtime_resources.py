import unittest

from backend.services.task_runtime_resources import TaskRuntimeResourceRegistry


class Stoppable:
    def __init__(self):
        self.stopped = False

    def set_stop_flag(self):
        self.stopped = True


class StopFlagObserver:
    def __init__(self, stop_flags, task_id):
        self.stop_flags = stop_flags
        self.task_id = task_id
        self.flag_when_stopped = None

    def set_stop_flag(self):
        self.flag_when_stopped = self.stop_flags.get(self.task_id)


class TaskRuntimeResourceRegistryTests(unittest.TestCase):
    def test_register_unregister_and_clear_are_idempotent(self):
        crawlers = {}
        downloaders = {}
        registry = TaskRuntimeResourceRegistry(crawlers, downloaders)
        crawler = Stoppable()
        downloader = Stoppable()

        registry.register_crawler("task-1", crawler)
        registry.register_file_downloader("task-1", downloader)

        self.assertIs(crawler, registry.task_crawler("task-1"))
        self.assertIs(downloader, registry.task_file_downloader("task-1"))

        registry.unregister_crawler("task-1")
        registry.unregister_crawler("task-1")
        registry.unregister_file_downloader("task-1")
        registry.unregister_file_downloader("task-1")

        self.assertEqual({}, crawlers)
        self.assertEqual({}, downloaders)

        registry.register_crawler("task-2", crawler)
        registry.register_file_downloader("task-2", downloader)
        registry.clear()

        self.assertEqual({}, crawlers)
        self.assertEqual({}, downloaders)

    def test_prepare_task_stop_marks_stop_flag_before_stopping_resources(self):
        stop_flags = {}
        crawler = StopFlagObserver(stop_flags, "task-1")
        downloader = StopFlagObserver(stop_flags, "task-1")
        registry = TaskRuntimeResourceRegistry({"task-1": crawler}, {"task-1": downloader})

        resources = registry.prepare_task_stop(
            "task-1",
            set_task_stop_flag=lambda task_id, stopped: stop_flags.__setitem__(task_id, stopped),
        )
        registry.request_stop_for_task(resources, fallback_crawler=None)

        self.assertTrue(crawler.flag_when_stopped)
        self.assertTrue(downloader.flag_when_stopped)

    def test_request_stop_for_task_uses_fallback_crawler_when_task_crawler_is_missing(self):
        downloader = Stoppable()
        fallback_crawler = Stoppable()
        registry = TaskRuntimeResourceRegistry({}, {"task-1": downloader})

        resources = registry.prepare_task_stop(
            "task-1",
            set_task_stop_flag=lambda _task_id, _stopped: None,
        )
        registry.request_stop_for_task(resources, fallback_crawler=fallback_crawler)

        self.assertTrue(fallback_crawler.stopped)
        self.assertTrue(downloader.stopped)

    def test_prepare_runtime_shutdown_marks_active_tasks_and_snapshots_resources(self):
        stop_flags = {}
        crawler = Stoppable()
        downloader = Stoppable()
        tasks = [
            ("task-1", {"status": "running"}),
            ("task-2", {"status": "completed"}),
        ]
        registry = TaskRuntimeResourceRegistry({"task-1": crawler}, {"task-1": downloader})

        snapshot = registry.prepare_runtime_shutdown(
            tasks,
            is_active_task_status=lambda status: status == "running",
            set_task_stop_flag=lambda task_id, stopped: stop_flags.__setitem__(task_id, stopped),
        )

        self.assertEqual({"task-1": True}, stop_flags)
        self.assertEqual(tasks, snapshot.tasks)
        self.assertEqual([crawler], snapshot.crawlers)
        self.assertEqual([downloader], snapshot.file_downloaders)


if __name__ == "__main__":
    unittest.main()
