import unittest
from unittest.mock import patch


class FileAIAnalysisEntryHelperTests(unittest.TestCase):
    def test_ensure_file_analysis_api_key_preserves_missing_key_error(self):
        from backend.services import file_ai_analysis_entry as entry
        from backend.services.ai_workflow_preflight import AIWorkflowPreflightError, MISSING_OPENAI_API_KEY_MESSAGE

        with patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=False):
            with self.assertRaises(AIWorkflowPreflightError) as raised:
                entry.ensure_file_analysis_api_key()

        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual(MISSING_OPENAI_API_KEY_MESSAGE, raised.exception.detail)
        self.assertEqual(f"400: {MISSING_OPENAI_API_KEY_MESSAGE}", str(raised.exception))

    def test_get_file_analysis_response_preserves_payload_shape(self):
        from backend.services import file_ai_analysis_entry as entry

        analysis = {"summary": "cached"}

        with patch.object(entry, "get_group_file_analysis", return_value=analysis) as get_analysis:
            result = entry.get_file_analysis_response("group-1", 123)

        self.assertEqual({"analysis": analysis}, result)
        get_analysis.assert_called_once_with("group-1", 123)

    def test_create_file_analysis_response_delegates_file_defaults_and_payload(self):
        from backend.services import file_ai_analysis_entry as entry

        analysis = {"summary": "created"}

        with (
            patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=True),
            patch.object(entry, "analyze_group_file", return_value=analysis) as analyze_file,
        ):
            result = entry.create_file_analysis_response("group-1", 456, True)

        self.assertEqual({"analysis": analysis}, result)
        analyze_file.assert_called_once_with(
            "group-1",
            456,
            force=True,
        )

    def test_create_file_analysis_response_checks_key_before_analysis(self):
        from backend.services import file_ai_analysis_entry as entry
        from backend.services.ai_workflow_preflight import AIWorkflowPreflightError

        with (
            patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=False),
            patch.object(entry, "analyze_group_file") as analyze_file,
        ):
            with self.assertRaises(AIWorkflowPreflightError):
                entry.create_file_analysis_response("group-1", 456, True)

        analyze_file.assert_not_called()

    def test_create_file_analysis_task_response_checks_key_and_delegates(self):
        from backend.services import file_ai_analysis_entry as entry

        with (
            patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=True),
            patch.object(entry, "create_file_ai_analysis_task", return_value={"task_id": "task-1"}) as create_task,
        ):
            result = entry.create_file_analysis_task_response("group-1", 123, True)

        self.assertEqual({"task_id": "task-1"}, result)
        create_task.assert_called_once_with("group-1", 123, True)

    def test_create_selected_file_analysis_task_response_checks_key_and_delegates(self):
        from backend.services import file_ai_analysis_entry as entry

        request = object()

        with (
            patch("backend.services.ai_workflow_preflight.has_openai_api_key", return_value=True),
            patch.object(
                entry,
                "create_selected_file_ai_analysis_task",
                return_value={"task_id": "task-1"},
            ) as create_task,
        ):
            result = entry.create_selected_file_analysis_task_response("group-1", request)

        self.assertEqual({"task_id": "task-1"}, result)
        create_task.assert_called_once_with("group-1", request)
