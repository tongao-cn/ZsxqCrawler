import unittest
from unittest.mock import patch


class CrawlWorkflowTests(unittest.TestCase):
    def test_crawl_launch_tasks_use_ingestion_workflow(self):
        from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
        from backend.services import crawl_workflow

        group_id = "51111112855254"
        historical_request = CrawlHistoricalRequest(pages=3, per_page=25)
        incremental_request = CrawlHistoricalRequest(pages=4, per_page=30)
        all_request = CrawlSettingsRequest(topicSource="official")
        latest_request = CrawlSettingsRequest(pagesPerBatch=15)
        range_request = CrawlTimeRangeRequest(lastDays=7, perPage=40)

        cases = [
            (
                "historical",
                crawl_workflow.create_historical_crawl_task,
                historical_request,
                "crawl_historical",
                "爬取历史数据 3 页 (群组: 51111112855254)",
                crawl_workflow.run_crawl_historical_task,
                (historical_request.pages, historical_request.per_page, historical_request),
            ),
            (
                "all",
                crawl_workflow.create_all_crawl_task,
                all_request,
                "crawl_all",
                "全量爬取所有历史数据 (群组: 51111112855254)",
                crawl_workflow.run_crawl_all_task,
                (all_request,),
            ),
            (
                "incremental",
                crawl_workflow.create_incremental_crawl_task,
                incremental_request,
                "crawl_incremental",
                "增量爬取历史数据 4 页 (群组: 51111112855254)",
                crawl_workflow.run_crawl_incremental_task,
                (incremental_request.pages, incremental_request.per_page, incremental_request),
            ),
            (
                "latest",
                crawl_workflow.launch_latest_crawl_task,
                latest_request,
                "crawl_latest_until_complete",
                "获取最新记录 (群组: 51111112855254)",
                crawl_workflow.run_crawl_latest_task,
                (latest_request,),
            ),
            (
                "range",
                crawl_workflow.create_time_range_crawl_task,
                range_request,
                "crawl_time_range",
                "按时间区间爬取 (群组: 51111112855254)",
                crawl_workflow.run_crawl_time_range_task,
                (range_request,),
            ),
        ]

        for case_name, launcher, request, task_type, description, task_func, task_args in cases:
            with self.subTest(case_name=case_name):
                with patch(
                    "backend.services.crawl_workflow.launch_task_recipe",
                    return_value={"task_id": f"task-{case_name}"},
                ) as launch:
                    response = launcher(group_id, request)

            self.assertEqual({"task_id": f"task-{case_name}"}, response)
            launch.assert_called_once()
            recipe = launch.call_args.args[0]
            self.assertEqual(task_type, recipe.task_type)
            self.assertEqual(description, recipe.description)
            self.assertEqual(task_func, recipe.task_func)
            self.assertEqual(group_id, recipe.ingestion_group_id)
            self.assertEqual(task_args, recipe.args)

    def test_crawl_launch_tasks_preserve_ingestion_conflict(self):
        from backend.schemas.crawl import CrawlHistoricalRequest
        from backend.services import crawl_workflow
        from backend.services.task_launch import TaskLaunchConflict

        existing = {"task_id": "task-old", "type": "crawl_historical", "status": "running"}

        with patch(
            "backend.services.crawl_workflow.launch_task_recipe",
            side_effect=TaskLaunchConflict(existing),
        ):
            with self.assertRaises(TaskLaunchConflict) as raised:
                crawl_workflow.create_historical_crawl_task("group-1", CrawlHistoricalRequest())

        self.assertEqual(existing, raised.exception.existing)

    def test_launch_or_reuse_latest_crawl_task_returns_existing_conflict_task(self):
        from backend.schemas.crawl import CrawlSettingsRequest
        from backend.services import crawl_workflow
        from backend.services.task_launch import TaskLaunchConflict

        request = CrawlSettingsRequest()

        with patch(
            "backend.services.crawl_workflow.launch_latest_crawl_task",
            side_effect=TaskLaunchConflict({"task_id": "task-existing"}),
        ):
            response, source = crawl_workflow.launch_or_reuse_latest_crawl_task("group-1", request)

        self.assertEqual("existing", source)
        self.assertEqual("task-existing", response["task_id"])

if __name__ == "__main__":
    unittest.main()
