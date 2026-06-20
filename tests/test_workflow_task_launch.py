import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch


class WorkflowTaskLaunchTests(unittest.TestCase):
    def test_launch_latest_crawl_task_uses_ingestion_workflow(self):
        from backend.schemas.crawl import CrawlSettingsRequest
        from backend.services import workflow_task_launch

        request = CrawlSettingsRequest(pagesPerBatch=15)

        with patch("backend.services.workflow_task_launch.launch_ingestion_task", return_value={"task_id": "task-1"}) as launch:
            response = workflow_task_launch.launch_latest_crawl_task("51111112855254", request)

        self.assertEqual({"task_id": "task-1"}, response)
        launch.assert_called_once_with(
            "crawl_latest_until_complete",
            "获取最新记录 (群组: 51111112855254)",
            workflow_task_launch.run_crawl_latest_task,
            "51111112855254",
            request,
        )

    def test_launch_or_reuse_latest_crawl_task_returns_existing_conflict_task(self):
        from backend.schemas.crawl import CrawlSettingsRequest
        from backend.services import workflow_task_launch
        from backend.services.task_launch import TaskLaunchConflict

        request = CrawlSettingsRequest()

        with patch(
            "backend.services.workflow_task_launch.launch_latest_crawl_task",
            side_effect=TaskLaunchConflict({"task_id": "task-existing"}),
        ):
            response, source = workflow_task_launch.launch_or_reuse_latest_crawl_task("group-1", request)

        self.assertEqual("existing", source)
        self.assertEqual("task-existing", response["task_id"])

    def test_create_daily_topic_analysis_task_uses_service_runner_and_metadata(self):
        from backend.services import workflow_task_launch

        with patch("backend.services.workflow_task_launch.launch_task", return_value={"task_id": "task-daily"}) as launch:
            response = workflow_task_launch.create_daily_topic_analysis_task(
                "51111112855254",
                date="2026-06-20",
                comments_per_topic=2,
            )

        self.assertEqual({"task_id": "task-daily"}, response)
        task_args = launch.call_args.args
        task_kwargs = launch.call_args.kwargs
        self.assertEqual("daily_topic_analysis", task_args[0])
        self.assertEqual(workflow_task_launch.run_daily_topic_analysis_task, task_args[2])
        self.assertEqual("51111112855254", task_args[3])
        self.assertEqual("2026-06-20", task_args[4].date)
        self.assertEqual(2, task_args[4].comments_per_topic)
        self.assertEqual({"group_id": "51111112855254", "report_date": "2026-06-20"}, task_kwargs["metadata"])

    def test_create_daily_stock_concept_task_uses_service_runner_and_metadata(self):
        from backend.services import workflow_task_launch

        with patch("backend.services.workflow_task_launch.launch_task", return_value={"task_id": "task-stock"}) as launch:
            response = workflow_task_launch.create_daily_stock_concept_task(
                "51111112855254",
                date="2026-06-20",
                comments_per_topic=3,
            )

        self.assertEqual({"task_id": "task-stock"}, response)
        task_args = launch.call_args.args
        task_kwargs = launch.call_args.kwargs
        self.assertEqual("daily_stock_concepts", task_args[0])
        self.assertEqual(workflow_task_launch.run_daily_stock_concept_task, task_args[2])
        self.assertEqual("51111112855254", task_args[3])
        self.assertEqual("2026-06-20", task_args[4].date)
        self.assertEqual(3, task_args[4].comments_per_topic)
        self.assertEqual({"group_id": "51111112855254", "report_date": "2026-06-20"}, task_kwargs["metadata"])

    def test_create_a_share_analysis_task_requires_api_key(self):
        from backend.services import workflow_task_launch

        with patch("backend.services.workflow_task_launch.has_openai_api_key", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "OpenAI API Key"):
                workflow_task_launch.create_a_share_analysis_task(group_id="51111112855254")

    def test_create_a_share_analysis_task_uses_service_runner_and_metadata(self):
        from backend.services import workflow_task_launch

        with patch("backend.services.workflow_task_launch.has_openai_api_key", return_value=True), patch(
            "backend.services.workflow_task_launch.launch_task",
            return_value={"task_id": "task-a-share"},
        ) as launch:
            response = workflow_task_launch.create_a_share_analysis_task(
                group_id="51111112855254",
                days=14,
                concurrency=2,
            )

        self.assertEqual({"task_id": "task-a-share"}, response)
        task_args = launch.call_args.args
        task_kwargs = launch.call_args.kwargs
        self.assertEqual("a_share_analysis", task_args[0])
        self.assertEqual(workflow_task_launch.run_a_share_analysis_task, task_args[2])
        self.assertEqual("51111112855254", task_args[3].group_id)
        self.assertEqual(14, task_args[3].days)
        self.assertEqual(2, task_args[3].concurrency)
        self.assertEqual({"group_id": "51111112855254"}, task_kwargs["metadata"])

    def test_export_a_share_analysis_to_tdx_returns_success_payload(self):
        from backend.services import workflow_task_launch

        async def fake_to_thread(func, *args, **kwargs):
            self.assertEqual(workflow_task_launch.export_a_share_rankings_to_tdx, func)
            self.assertEqual((None, None), args)
            self.assertEqual("51111112855254", kwargs["group_id"])
            self.assertEqual("纪要又要", kwargs["group_name"])
            return {"total_written": 3}

        with patch("backend.services.workflow_task_launch.asyncio.to_thread", side_effect=fake_to_thread):
            result = asyncio.run(
                workflow_task_launch.export_a_share_analysis_to_tdx(
                    group_id="51111112855254",
                    group_name="纪要又要",
                )
            )

        self.assertEqual({"success": True, "total_written": 3}, result)

    def test_script_entrypoints_do_not_import_routes(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            "scripts/export_daily_review_topics.py",
            "scripts/run_zsxq_topic_recommendation_refresh.py",
        ):
            text = (root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("backend.routes", text, relative_path)


if __name__ == "__main__":
    unittest.main()
