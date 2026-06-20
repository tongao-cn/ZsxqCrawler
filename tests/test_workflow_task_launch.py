import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch


class WorkflowTaskLaunchTests(unittest.TestCase):
    def test_crawl_launch_tasks_use_ingestion_workflow(self):
        from backend.schemas.crawl import CrawlHistoricalRequest, CrawlSettingsRequest, CrawlTimeRangeRequest
        from backend.services import workflow_task_launch

        group_id = "51111112855254"
        historical_request = CrawlHistoricalRequest(pages=3, per_page=25)
        incremental_request = CrawlHistoricalRequest(pages=4, per_page=30)
        all_request = CrawlSettingsRequest(topicSource="official")
        latest_request = CrawlSettingsRequest(pagesPerBatch=15)
        range_request = CrawlTimeRangeRequest(lastDays=7, perPage=40)

        cases = [
            (
                "historical",
                workflow_task_launch.create_historical_crawl_task,
                historical_request,
                "crawl_historical",
                "爬取历史数据 3 页 (群组: 51111112855254)",
                workflow_task_launch.run_crawl_historical_task,
                (historical_request.pages, historical_request.per_page, historical_request),
            ),
            (
                "all",
                workflow_task_launch.create_all_crawl_task,
                all_request,
                "crawl_all",
                "全量爬取所有历史数据 (群组: 51111112855254)",
                workflow_task_launch.run_crawl_all_task,
                (all_request,),
            ),
            (
                "incremental",
                workflow_task_launch.create_incremental_crawl_task,
                incremental_request,
                "crawl_incremental",
                "增量爬取历史数据 4 页 (群组: 51111112855254)",
                workflow_task_launch.run_crawl_incremental_task,
                (incremental_request.pages, incremental_request.per_page, incremental_request),
            ),
            (
                "latest",
                workflow_task_launch.launch_latest_crawl_task,
                latest_request,
                "crawl_latest_until_complete",
                "获取最新记录 (群组: 51111112855254)",
                workflow_task_launch.run_crawl_latest_task,
                (latest_request,),
            ),
            (
                "range",
                workflow_task_launch.create_time_range_crawl_task,
                range_request,
                "crawl_time_range",
                "按时间区间爬取 (群组: 51111112855254)",
                workflow_task_launch.run_crawl_time_range_task,
                (range_request,),
            ),
        ]

        for case_name, launcher, request, task_type, description, task_func, task_args in cases:
            with self.subTest(case_name=case_name):
                with patch(
                    "backend.services.workflow_task_launch.launch_ingestion_task",
                    return_value={"task_id": f"task-{case_name}"},
                ) as launch:
                    response = launcher(group_id, request)

            self.assertEqual({"task_id": f"task-{case_name}"}, response)
            launch.assert_called_once_with(
                task_type,
                description,
                task_func,
                group_id,
                *task_args,
            )

    def test_crawl_launch_tasks_preserve_ingestion_conflict(self):
        from backend.schemas.crawl import CrawlHistoricalRequest
        from backend.services import workflow_task_launch
        from backend.services.task_launch import TaskLaunchConflict

        existing = {"task_id": "task-old", "type": "crawl_historical", "status": "running"}

        with patch(
            "backend.services.workflow_task_launch.launch_ingestion_task",
            side_effect=TaskLaunchConflict(existing),
        ):
            with self.assertRaises(TaskLaunchConflict) as raised:
                workflow_task_launch.create_historical_crawl_task("group-1", CrawlHistoricalRequest())

        self.assertEqual(existing, raised.exception.existing)

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

    def test_create_columns_fetch_task_uses_ingestion_launcher_and_running_status(self):
        from backend.services import workflow_task_launch

        request = object()

        with (
            patch(
                "backend.services.workflow_task_launch.launch_ingestion_task",
                return_value={"task_id": "task-1", "message": workflow_task_launch.COLUMNS_FETCH_CREATED_MESSAGE},
            ) as launch,
            patch("backend.services.workflow_task_launch.update_task") as update_task,
        ):
            response = workflow_task_launch.create_columns_fetch_task("123", request)
            on_created = launch.call_args.kwargs["on_created"]
            on_created("task-1")

        self.assertEqual(
            {"success": True, "task_id": "task-1", "message": workflow_task_launch.COLUMNS_FETCH_CREATED_MESSAGE},
            response,
        )
        launch.assert_called_once()
        task_args = launch.call_args.args
        task_kwargs = launch.call_args.kwargs
        self.assertEqual("columns_fetch", task_args[0])
        self.assertEqual("采集专栏内容 (群组: 123)", task_args[1])
        self.assertEqual(workflow_task_launch.run_columns_fetch_task, task_args[2])
        self.assertEqual("123", task_args[3])
        self.assertEqual(request, task_args[4])
        self.assertEqual(workflow_task_launch.COLUMNS_FETCH_CREATED_MESSAGE, task_kwargs["message"])
        update_task.assert_called_once_with("task-1", "running", workflow_task_launch.COLUMNS_FETCH_RUNNING_MESSAGE)

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

    def test_create_daily_topic_crawl_and_analysis_task_uses_service_runner_and_metadata(self):
        from backend.schemas.crawl import CrawlSettingsRequest
        from backend.services import workflow_task_launch

        crawl_settings = CrawlSettingsRequest(pagesPerBatch=15)

        with patch("backend.services.workflow_task_launch.launch_task", return_value={"task_id": "task-today"}) as launch:
            response = workflow_task_launch.create_daily_topic_crawl_and_analysis_task(
                "51111112855254",
                date="2026-06-20",
                comments_per_topic=2,
                crawl_latest_first=False,
                crawl_settings=crawl_settings,
            )

        self.assertEqual({"task_id": "task-today"}, response)
        task_args = launch.call_args.args
        task_kwargs = launch.call_args.kwargs
        self.assertEqual("daily_topic_crawl_and_analysis", task_args[0])
        self.assertEqual(workflow_task_launch.run_daily_topic_crawl_and_analysis_task, task_args[2])
        self.assertEqual("51111112855254", task_args[3])
        self.assertEqual("2026-06-20", task_args[4].date)
        self.assertEqual(2, task_args[4].comments_per_topic)
        self.assertFalse(task_args[4].crawl_latest_first)
        self.assertEqual(crawl_settings, task_args[4].crawl_settings)
        self.assertEqual({"group_id": "51111112855254", "report_date": "2026-06-20"}, task_kwargs["metadata"])

    def test_run_daily_topic_crawl_and_analysis_task_skips_crawl_when_disabled(self):
        from backend.services import workflow_task_launch

        request = workflow_task_launch.DailyTopicCrawlAndAnalysisTaskRequest(
            date="2026-06-20",
            comments_per_topic=2,
            crawl_latest_first=False,
        )

        with (
            patch("backend.services.workflow_task_launch.update_task") as update_task,
            patch("backend.services.workflow_task_launch.run_crawl_latest_task") as run_crawl_latest_task,
            patch("backend.services.workflow_task_launch.analyze_daily_topics", return_value={"report": []}) as analyze,
            patch("backend.services.workflow_task_launch.is_task_stopped", return_value=False),
        ):
            workflow_task_launch.run_daily_topic_crawl_and_analysis_task("task-1", "51111112855254", request)

        run_crawl_latest_task.assert_not_called()
        analyze.assert_called_once()
        call_args, call_kwargs = analyze.call_args
        self.assertEqual(("51111112855254", "2026-06-20"), call_args)
        self.assertEqual(2, call_kwargs["comments_per_topic"])
        self.assertTrue(callable(call_kwargs["log_callback"]))
        update_task.assert_any_call("task-1", "running", "开始每日抓取与 AI 分析...")
        update_task.assert_any_call("task-1", "completed", "每日抓取与 AI 分析完成", {"report": []})

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
                model="test-model",
                api_base="https://example.test/v1",
                wire_api="chat_completions",
                reasoning_effort="low",
                start_date="2026-05-01",
                end_date="2026-05-07",
                reset_start_date="2026-05-01",
                reset_end_date="2026-05-02",
            )

        self.assertEqual({"task_id": "task-a-share"}, response)
        task_args = launch.call_args.args
        task_kwargs = launch.call_args.kwargs
        self.assertEqual("a_share_analysis", task_args[0])
        self.assertEqual(workflow_task_launch.run_a_share_analysis_task, task_args[2])
        self.assertEqual("51111112855254", task_args[3].group_id)
        self.assertEqual(14, task_args[3].days)
        self.assertEqual(2, task_args[3].concurrency)
        self.assertEqual("test-model", task_args[3].model)
        self.assertEqual("https://example.test/v1", task_args[3].api_base)
        self.assertEqual("chat_completions", task_args[3].wire_api)
        self.assertEqual("low", task_args[3].reasoning_effort)
        self.assertEqual("2026-05-01", task_args[3].start_date)
        self.assertEqual("2026-05-07", task_args[3].end_date)
        self.assertEqual("2026-05-01", task_args[3].reset_start_date)
        self.assertEqual("2026-05-02", task_args[3].reset_end_date)
        self.assertEqual({"group_id": "51111112855254"}, task_kwargs["metadata"])

    def test_run_a_share_analysis_task_fails_fast_without_api_key(self):
        from backend.services import workflow_task_launch

        request = workflow_task_launch.AShareAnalysisTaskRequest(group_id="51111112855254")
        with (
            patch("backend.services.workflow_task_launch.has_openai_api_key", return_value=False),
            patch("backend.services.workflow_task_launch.update_task") as update_task,
            patch("backend.services.workflow_task_launch.add_task_log") as add_task_log,
            patch("backend.services.workflow_task_launch.run_analysis") as run_analysis,
        ):
            workflow_task_launch.run_a_share_analysis_task("task-a-share", request)

        update_task.assert_called_once_with(
            "task-a-share",
            "failed",
            workflow_task_launch.A_SHARE_MISSING_API_KEY_MESSAGE,
        )
        add_task_log.assert_called_once_with("task-a-share", f"❌ {workflow_task_launch.A_SHARE_MISSING_API_KEY_MESSAGE}")
        run_analysis.assert_not_called()

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
