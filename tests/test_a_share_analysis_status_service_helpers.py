import unittest
from unittest.mock import call, patch


class AShareAnalysisStatusServiceHelperTests(unittest.TestCase):
    def test_analysis_defaults_payload_matches_endpoint_shape(self):
        from backend.services import a_share_analysis_status_service as service

        self.assertEqual(
            {
                "days": 21,
                "concurrency": service.A_SHARE_DEFAULT_CONCURRENCY,
                "model": service.A_SHARE_DEFAULT_MODEL,
                "api_base": service.A_SHARE_DEFAULT_API_BASE,
                "wire_api": service.A_SHARE_DEFAULT_WIRE_API,
                "reasoning_effort": service.A_SHARE_DEFAULT_REASONING_EFFORT,
                "ranking_windows": list(service.A_SHARE_DEFAULT_RANKING_WINDOWS),
            },
            service._analysis_defaults_payload(),
        )

    def test_get_a_share_analysis_status_payload_preserves_success_payload_shape(self):
        import asyncio

        from backend.services import a_share_analysis_status_service as service

        summary = {"rows_count": 7, "processed_items": 5}
        latest_task = {"id": "latest"}
        running_task = {"id": "running"}
        storage = {"enabled": True, "mode": "postgres"}
        latest_export = {"total_written": 3}

        with (
            patch.object(service, "get_analysis_summary", return_value=summary) as get_summary,
            patch.object(service, "_a_share_status_tasks", return_value=(latest_task, running_task)) as get_tasks,
            patch.object(service, "_a_share_storage_status", return_value=storage) as get_storage_status,
            patch.object(service, "_latest_a_share_tdx_export", return_value=latest_export) as get_latest_export,
            patch.object(service, "has_openai_api_key", return_value=True) as has_api_key,
        ):
            result = asyncio.run(service.get_a_share_analysis_status_payload(" 51111112855254 "))

        self.assertEqual(
            {
                "summary": summary,
                "group_id": "51111112855254",
                "defaults": service._analysis_defaults_payload(),
                "api_key_configured": True,
                "latest_task": latest_task,
                "running_task": running_task,
                "storage": storage,
                "latest_tdx_export": latest_export,
            },
            result,
        )
        get_summary.assert_called_once_with(group_id="51111112855254")
        get_tasks.assert_called_once_with("51111112855254")
        get_storage_status.assert_awaited_once_with(summary, "51111112855254")
        get_latest_export.assert_awaited_once_with("51111112855254")
        has_api_key.assert_called_once_with()

    def test_a_share_storage_status_falls_back_to_file_counts(self):
        import asyncio

        from backend.services import a_share_analysis_status_service as service

        summary = {"rows_count": 7, "processed_items": 5}

        with patch.object(service, "get_storage_health", side_effect=RuntimeError("pg down")) as get_storage_health:
            result = asyncio.run(service._a_share_storage_status(summary, "51111112855254"))

        self.assertEqual(
            {
                "enabled": False,
                "mode": "file_fallback",
                "label": "本地文件降级（PostgreSQL 不可用: pg down）",
                "daily_rows": 7,
                "processed_rows": 5,
            },
            result,
        )
        get_storage_health.assert_called_once_with(group_id="51111112855254")

    def test_latest_a_share_tdx_export_swallows_lookup_errors(self):
        import asyncio

        from backend.services import a_share_analysis_status_service as service

        with patch.object(service, "get_latest_tdx_export", side_effect=RuntimeError("export down")) as get_latest:
            result = asyncio.run(service._latest_a_share_tdx_export("51111112855254"))

        self.assertIsNone(result)
        get_latest.assert_called_once_with("51111112855254")

    def test_a_share_status_tasks_queries_latest_and_running_for_scope(self):
        from backend.services import a_share_analysis_status_service as service

        latest_task = {"id": "latest"}
        running_task = {"id": "running"}

        with patch.object(service, "get_latest_task_by_type", side_effect=[latest_task, running_task]) as get_latest:
            result = service._a_share_status_tasks("51111112855254")

        self.assertEqual((latest_task, running_task), result)
        self.assertEqual(
            [
                call("a_share_analysis", group_id="51111112855254"),
                call("a_share_analysis", status="running", group_id="51111112855254"),
            ],
            get_latest.call_args_list,
        )

    def test_a_share_status_tasks_keeps_global_tasks_separate(self):
        from datetime import datetime

        from backend.services import a_share_analysis_status_service as service

        class Store:
            def list_tasks(self, limit=None):
                tasks = [
                    {
                        "task_id": "group-running",
                        "type": "a_share_analysis",
                        "status": "running",
                        "group_id": "51111112855254",
                        "created_at": datetime(2026, 1, 3, 9, 0, 0),
                    },
                    {
                        "task_id": "global-running",
                        "type": "a_share_analysis",
                        "status": "running",
                        "group_id": None,
                        "created_at": datetime(2026, 1, 2, 9, 0, 0),
                    },
                    {
                        "task_id": "global-completed",
                        "type": "a_share_analysis",
                        "status": "completed",
                        "group_id": None,
                        "created_at": datetime(2026, 1, 1, 9, 0, 0),
                    },
                ]
                return tasks[:limit] if limit is not None else tasks

        with patch("backend.services.task_runtime.get_task_store", return_value=Store()):
            latest_task, running_task = service._a_share_status_tasks(None)

        self.assertEqual("global-running", latest_task["task_id"])
        self.assertEqual("global-running", running_task["task_id"])
