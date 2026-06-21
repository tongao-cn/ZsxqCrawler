import unittest
from unittest.mock import Mock, patch


class AIWorkflowPreflightTests(unittest.TestCase):
    def test_require_openai_api_key_raises_typed_error_when_missing(self):
        from backend.services import ai_workflow_preflight as preflight

        with patch.object(preflight, "has_openai_api_key", return_value=False):
            with self.assertRaises(preflight.AIWorkflowPreflightError) as raised:
                preflight.require_openai_api_key()

        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual(preflight.MISSING_OPENAI_API_KEY_MESSAGE, raised.exception.detail)
        self.assertEqual(f"400: {preflight.MISSING_OPENAI_API_KEY_MESSAGE}", str(raised.exception))

    def test_require_openai_api_key_returns_when_configured(self):
        from backend.services import ai_workflow_preflight as preflight

        with patch.object(preflight, "has_openai_api_key", return_value=True):
            self.assertIsNone(preflight.require_openai_api_key())

    def test_fail_task_if_openai_api_key_missing_marks_failed_and_logs(self):
        from backend.services import ai_workflow_preflight as preflight

        update_task_state = Mock()
        add_task_log = Mock()

        with patch.object(preflight, "has_openai_api_key", return_value=False):
            missing = preflight.fail_task_if_openai_api_key_missing(
                "task-ai",
                update_task_state=update_task_state,
                add_task_log=add_task_log,
            )

        self.assertTrue(missing)
        update_task_state.assert_called_once_with("task-ai", "failed", preflight.MISSING_OPENAI_API_KEY_MESSAGE)
        add_task_log.assert_called_once_with("task-ai", f"❌ {preflight.MISSING_OPENAI_API_KEY_MESSAGE}")

    def test_fail_task_if_openai_api_key_missing_returns_false_when_configured(self):
        from backend.services import ai_workflow_preflight as preflight

        update_task_state = Mock()
        add_task_log = Mock()

        with patch.object(preflight, "has_openai_api_key", return_value=True):
            missing = preflight.fail_task_if_openai_api_key_missing(
                "task-ai",
                update_task_state=update_task_state,
                add_task_log=add_task_log,
            )

        self.assertFalse(missing)
        update_task_state.assert_not_called()
        add_task_log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
