import unittest
from unittest.mock import patch


class DailyAnalysisWorkflowTests(unittest.TestCase):
    def test_create_daily_topic_analysis_task_uses_service_runner_and_metadata(self):
        from backend.services import daily_analysis_workflow as workflow

        with patch(
            "backend.services.daily_analysis_workflow.launch_task_recipe",
            return_value={"task_id": "task-daily"},
        ) as launch:
            response = workflow.create_daily_topic_analysis_task(
                "51111112855254",
                date="2026-06-20",
                comments_per_topic=2,
            )

        self.assertEqual({"task_id": "task-daily"}, response)
        recipe = launch.call_args.args[0]
        self.assertEqual("daily_topic_analysis", recipe.task_type)
        self.assertEqual("生成每日话题 AI 报告 (群组: 51111112855254)", recipe.description)
        self.assertEqual(workflow.run_daily_topic_analysis_task, recipe.task_func)
        self.assertEqual("51111112855254", recipe.args[0])
        self.assertEqual("2026-06-20", recipe.args[1].date)
        self.assertEqual(2, recipe.args[1].comments_per_topic)
        self.assertEqual({"group_id": "51111112855254", "report_date": "2026-06-20"}, recipe.metadata)

    def test_create_daily_topic_crawl_and_analysis_task_uses_service_runner_and_metadata(self):
        from backend.schemas.crawl import CrawlSettingsRequest
        from backend.services import daily_analysis_workflow as workflow

        crawl_settings = CrawlSettingsRequest(pagesPerBatch=15)

        with patch(
            "backend.services.daily_analysis_workflow.launch_task_recipe",
            return_value={"task_id": "task-today"},
        ) as launch:
            response = workflow.create_daily_topic_crawl_and_analysis_task(
                "51111112855254",
                date="2026-06-20",
                comments_per_topic=2,
                crawl_latest_first=False,
                crawl_settings=crawl_settings,
            )

        self.assertEqual({"task_id": "task-today"}, response)
        recipe = launch.call_args.args[0]
        self.assertEqual("daily_topic_crawl_and_analysis", recipe.task_type)
        self.assertEqual("每日抓取与 AI 分析 (群组: 51111112855254)", recipe.description)
        self.assertEqual(workflow.run_daily_topic_crawl_and_analysis_task, recipe.task_func)
        self.assertEqual("51111112855254", recipe.args[0])
        self.assertEqual("2026-06-20", recipe.args[1].date)
        self.assertEqual(2, recipe.args[1].comments_per_topic)
        self.assertFalse(recipe.args[1].crawl_latest_first)
        self.assertEqual(crawl_settings, recipe.args[1].crawl_settings)
        self.assertEqual({"group_id": "51111112855254", "report_date": "2026-06-20"}, recipe.metadata)

    def test_run_daily_topic_crawl_and_analysis_task_skips_crawl_when_disabled(self):
        from backend.services import daily_analysis_workflow as workflow

        request = workflow.DailyTopicCrawlAndAnalysisTaskRequest(
            date="2026-06-20",
            comments_per_topic=2,
            crawl_latest_first=False,
        )

        with (
            patch("backend.services.daily_analysis_workflow.update_task") as update_task,
            patch("backend.services.daily_analysis_workflow.run_crawl_latest_task") as run_crawl_latest_task,
            patch("backend.services.daily_analysis_workflow.analyze_daily_topics", return_value={"report": []}) as analyze,
            patch("backend.services.daily_analysis_workflow.is_task_stopped", return_value=False),
        ):
            workflow.run_daily_topic_crawl_and_analysis_task("task-1", "51111112855254", request)

        run_crawl_latest_task.assert_not_called()
        analyze.assert_called_once()
        call_args, call_kwargs = analyze.call_args
        self.assertEqual(("51111112855254", "2026-06-20"), call_args)
        self.assertEqual(2, call_kwargs["comments_per_topic"])
        self.assertTrue(callable(call_kwargs["log_callback"]))
        update_task.assert_any_call("task-1", "running", "开始每日抓取与 AI 分析...")
        update_task.assert_any_call("task-1", "completed", "每日抓取与 AI 分析完成", {"report": []})

    def test_create_daily_stock_concept_task_uses_service_runner_and_metadata(self):
        from backend.services import daily_analysis_workflow as workflow

        with patch(
            "backend.services.daily_analysis_workflow.launch_task_recipe",
            return_value={"task_id": "task-stock"},
        ) as launch:
            response = workflow.create_daily_stock_concept_task(
                "51111112855254",
                date="2026-06-20",
                comments_per_topic=3,
            )

        self.assertEqual({"task_id": "task-stock"}, response)
        recipe = launch.call_args.args[0]
        self.assertEqual("daily_stock_concepts", recipe.task_type)
        self.assertEqual("提取每日股票概念 (群组: 51111112855254)", recipe.description)
        self.assertEqual(workflow.run_daily_stock_concept_task, recipe.task_func)
        self.assertEqual("51111112855254", recipe.args[0])
        self.assertEqual("2026-06-20", recipe.args[1].date)
        self.assertEqual(3, recipe.args[1].comments_per_topic)
        self.assertEqual({"group_id": "51111112855254", "report_date": "2026-06-20"}, recipe.metadata)

if __name__ == "__main__":
    unittest.main()
