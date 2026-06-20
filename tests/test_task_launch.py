import unittest
from unittest.mock import patch


def fake_task(*args):
    return args


class TaskLaunchTests(unittest.TestCase):
    def test_ingestion_conflict_detail_keeps_public_shape(self):
        from backend.services.task_launch import ingestion_conflict_detail

        detail = ingestion_conflict_detail({"task_id": "task-1", "type": "crawl_all", "status": "running"})

        self.assertEqual(
            {
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-1",
                "type": "crawl_all",
                "status": "running",
            },
            detail,
        )

    def test_launch_ingestion_task_creates_locked_task_and_enqueues_with_group_first(self):
        from backend.services.task_launch import launch_ingestion_task

        with (
            patch("backend.services.task_launch.create_ingestion_task", return_value=("task-1", None)) as create_task,
            patch("backend.services.task_launch.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = launch_ingestion_task(
                "collect_files",
                "收集文件列表",
                fake_task,
                "group-1",
                "request",
                message="已启动",
            )

        create_task.assert_called_once_with("collect_files", "收集文件列表", "group-1")
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-1", "group-1", "request")
        self.assertEqual({"task_id": "task-1", "message": "已启动"}, response)

    def test_launch_ingestion_task_can_keep_explicit_runtime_args(self):
        from backend.services.task_launch import launch_ingestion_task

        with (
            patch("backend.services.task_launch.create_ingestion_task", return_value=("task-1", None)),
            patch("backend.services.task_launch.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            launch_ingestion_task(
                "collect_files",
                "收集文件列表",
                fake_task,
                "group-1",
                "group-1",
                "request",
                prepend_group_id_to_args=False,
            )

        enqueue_runtime_task.assert_called_once_with(fake_task, "task-1", "group-1", "request")

    def test_launch_ingestion_task_raises_conflict_without_enqueuing(self):
        from backend.services.task_launch import TaskLaunchConflict, launch_ingestion_task

        existing = {"task_id": "task-0", "type": "crawl_all", "status": "running"}

        with (
            patch("backend.services.task_launch.create_ingestion_task", return_value=(None, existing)),
            patch("backend.services.task_launch.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            with self.assertRaises(TaskLaunchConflict) as raised:
                launch_ingestion_task("collect_files", "收集文件列表", fake_task, "group-1")

        self.assertEqual(existing, raised.exception.existing)
        enqueue_runtime_task.assert_not_called()

    def test_launch_ingestion_task_rejects_non_ingestion_workflow(self):
        from backend.services.task_launch import launch_ingestion_task

        with self.assertRaises(ValueError):
            launch_ingestion_task("daily_stock_concepts", "提取每日股票概念", fake_task, "group-1")

    def test_launch_task_attaches_group_metadata_and_enqueues_args(self):
        from backend.services.task_launch import launch_task

        with (
            patch("backend.services.task_launch.create_task", return_value="task-2") as create_task,
            patch("backend.services.task_launch.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = launch_task(
                "daily_topic_analysis",
                "生成每日话题 AI 报告",
                fake_task,
                "group-1",
                "request",
                group_id="group-1",
                metadata={"report_date": "2026-06-20"},
            )

        create_task.assert_called_once_with(
            "daily_topic_analysis",
            "生成每日话题 AI 报告",
            metadata={"group_id": "group-1", "report_date": "2026-06-20"},
        )
        enqueue_runtime_task.assert_called_once_with(fake_task, "task-2", "group-1", "request")
        self.assertEqual({"task_id": "task-2", "message": "任务已创建，正在后台执行"}, response)

    def test_launch_task_rejects_unregistered_workflow(self):
        from backend.services.task_launch import launch_task

        with self.assertRaises(ValueError):
            launch_task("missing_task_type", "missing", fake_task)


if __name__ == "__main__":
    unittest.main()
