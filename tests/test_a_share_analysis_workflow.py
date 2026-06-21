import asyncio
import unittest
from unittest.mock import patch


class AShareAnalysisWorkflowTests(unittest.TestCase):
    def test_create_a_share_analysis_task_requires_api_key(self):
        from backend.services import a_share_analysis_workflow as workflow
        from backend.services.ai_workflow_preflight import AIWorkflowPreflightError, MISSING_OPENAI_API_KEY_MESSAGE

        with patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=False):
            with self.assertRaises(AIWorkflowPreflightError) as raised:
                workflow.create_a_share_analysis_task(group_id="51111112855254")
        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual(MISSING_OPENAI_API_KEY_MESSAGE, raised.exception.detail)

    def test_create_a_share_analysis_task_uses_service_runner_and_metadata(self):
        from backend.services import a_share_analysis_workflow as workflow

        with patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=True), patch(
            "backend.services.a_share_analysis_workflow.launch_task_recipe",
            return_value={"task_id": "task-a-share"},
        ) as launch:
            response = workflow.create_a_share_analysis_task(
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
        recipe = launch.call_args.args[0]
        request = recipe.args[0]
        self.assertEqual("a_share_analysis", recipe.task_type)
        self.assertEqual("A股公司分析（群组 51111112855254，2026-05-01 ~ 2026-05-07）", recipe.description)
        self.assertEqual(workflow.run_a_share_analysis_task, recipe.task_func)
        self.assertEqual("51111112855254", request.group_id)
        self.assertEqual(14, request.days)
        self.assertEqual(2, request.concurrency)
        self.assertEqual("test-model", request.model)
        self.assertEqual("https://example.test/v1", request.api_base)
        self.assertEqual("chat_completions", request.wire_api)
        self.assertEqual("low", request.reasoning_effort)
        self.assertEqual("2026-05-01", request.start_date)
        self.assertEqual("2026-05-07", request.end_date)
        self.assertEqual("2026-05-01", request.reset_start_date)
        self.assertEqual("2026-05-02", request.reset_end_date)
        self.assertEqual({"group_id": "51111112855254"}, recipe.metadata)

    def test_run_a_share_analysis_task_fails_fast_without_api_key(self):
        from backend.services import a_share_analysis_workflow as workflow
        from backend.services.ai_workflow_preflight import MISSING_OPENAI_API_KEY_MESSAGE

        request = workflow.AShareAnalysisTaskRequest(group_id="51111112855254")
        with (
            patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=False),
            patch("backend.services.a_share_analysis_workflow.update_task") as update_task,
            patch("backend.services.a_share_analysis_workflow.add_task_log") as add_task_log,
            patch("backend.services.a_share_analysis_workflow.run_analysis") as run_analysis,
        ):
            workflow.run_a_share_analysis_task("task-a-share", request)

        update_task.assert_called_once_with(
            "task-a-share",
            "failed",
            MISSING_OPENAI_API_KEY_MESSAGE,
        )
        add_task_log.assert_called_once_with("task-a-share", f"❌ {MISSING_OPENAI_API_KEY_MESSAGE}")
        run_analysis.assert_not_called()

    def test_export_a_share_analysis_to_tdx_returns_success_payload(self):
        from backend.services import a_share_analysis_workflow as workflow

        async def fake_to_thread(func, *args, **kwargs):
            self.assertEqual(workflow.export_a_share_rankings_to_tdx, func)
            self.assertEqual((None, None), args)
            self.assertEqual("51111112855254", kwargs["group_id"])
            self.assertEqual("纪要又要", kwargs["group_name"])
            return {"total_written": 3}

        with patch("backend.services.a_share_analysis_workflow.asyncio.to_thread", side_effect=fake_to_thread):
            result = asyncio.run(
                workflow.export_a_share_analysis_to_tdx(
                    group_id="51111112855254",
                    group_name="纪要又要",
                )
            )

        self.assertEqual({"success": True, "total_written": 3}, result)

if __name__ == "__main__":
    unittest.main()
