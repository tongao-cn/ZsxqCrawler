import unittest
from unittest.mock import patch


class RetentionRoutesHelperTests(unittest.TestCase):
    def test_cleanup_response_runs_preview_when_dry_run_is_true(self):
        from backend.routes.retention_routes import RetentionCleanupRequest, _retention_cleanup_response

        request = RetentionCleanupRequest(retentionDays=400, dryRun=True)
        preview_result = {"matched_topics": 2}

        with patch(
            "backend.routes.retention_routes.preview_group_retention_cleanup",
            return_value=preview_result,
        ) as preview:
            result = _retention_cleanup_response("303", request)

        self.assertEqual(preview_result, result)
        preview.assert_called_once_with("303", retention_days=400)

    def test_cleanup_response_creates_task_when_dry_run_is_false(self):
        from backend.routes.retention_routes import RetentionCleanupRequest, _retention_cleanup_response

        request = RetentionCleanupRequest(retentionDays=400, dryRun=False)

        with patch(
            "backend.routes.retention_routes.create_retention_cleanup_task",
            return_value={"task_id": "task-retention"},
        ) as create_task:
            result = _retention_cleanup_response("303", request)

        self.assertEqual({"task_id": "task-retention"}, result)
        create_task.assert_called_once_with("303", retention_days=400)


if __name__ == "__main__":
    unittest.main()
