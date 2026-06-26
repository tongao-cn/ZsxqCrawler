import unittest


class WorkflowRegistryTests(unittest.TestCase):
    def test_registry_contains_current_workflow_types(self):
        from backend.services.workflow_registry import WORKFLOW_SPECS

        self.assertEqual(
            {
                "columns_fetch",
                "crawl_all",
                "crawl_historical",
                "crawl_incremental",
                "crawl_latest_until_complete",
                "crawl_time_range",
                "collect_files",
                "download_files",
                "download_filtered_files",
                "download_selected_files",
                "download_single_file",
                "sync_files_from_topics",
                "retention_cleanup",
                "analyze_file",
                "analyze_files",
                "daily_stock_concepts",
                "daily_topic_analysis",
                "daily_topic_crawl_and_analysis",
                "research_radar",
                "a_share_analysis",
                "stock_question_analysis",
                "stock_topic_analysis",
                "stock_topic_analysis_batch",
            },
            set(WORKFLOW_SPECS),
        )

    def test_ingestion_workflows_drive_runtime_lock_compatibility(self):
        from backend.services.task_runtime import INGESTION_LOCK_TYPES
        from backend.services.workflow_registry import (
            INGESTION_LOCK_CATEGORY,
            INGESTION_WORKFLOW_TYPES,
            WORKFLOW_SPECS,
            workflow_types_for_lock,
        )

        self.assertEqual(INGESTION_WORKFLOW_TYPES, workflow_types_for_lock(INGESTION_LOCK_CATEGORY))
        self.assertEqual(INGESTION_WORKFLOW_TYPES, INGESTION_LOCK_TYPES)
        self.assertIn("columns_fetch", INGESTION_LOCK_TYPES)
        self.assertIn("download_single_file", INGESTION_LOCK_TYPES)
        self.assertNotIn("analyze_file", INGESTION_LOCK_TYPES)
        self.assertTrue(
            all(
                WORKFLOW_SPECS[task_type].lock_category == INGESTION_LOCK_CATEGORY
                for task_type in INGESTION_WORKFLOW_TYPES
            )
        )

    def test_specs_capture_current_scope_and_recovery_contract(self):
        from backend.services.workflow_registry import get_workflow_spec

        download_spec = get_workflow_spec("download_selected_files")
        self.assertEqual("选中文件下载", download_spec.display_name)
        self.assertEqual("group", download_spec.scope)
        self.assertEqual("ingestion", download_spec.lock_category)
        self.assertTrue(download_spec.cancellable)
        self.assertEqual("none", download_spec.retry_policy)
        self.assertEqual("none", download_spec.checkpoint_policy)

        a_share_spec = get_workflow_spec("a_share_analysis")
        self.assertEqual("股票推荐池", a_share_spec.display_name)
        self.assertEqual("optional_group", a_share_spec.scope)
        self.assertIsNone(a_share_spec.lock_category)
        self.assertFalse(a_share_spec.cancellable)
        self.assertEqual("business_state", a_share_spec.checkpoint_policy)

        self.assertIsNone(get_workflow_spec("unknown_task"))

    def test_research_radar_workflow_is_registered_as_group_runtime_task(self):
        from backend.services.workflow_registry import get_workflow_spec

        spec = get_workflow_spec("research_radar")

        self.assertIsNotNone(spec)
        self.assertEqual("研究雷达", spec.display_name)
        self.assertEqual("group", spec.scope)
        self.assertIsNone(spec.lock_category)
        self.assertTrue(spec.cancellable)


if __name__ == "__main__":
    unittest.main()
