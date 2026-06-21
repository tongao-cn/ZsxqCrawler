import unittest
from unittest.mock import patch


class ColumnsWorkflowTests(unittest.TestCase):
    def test_create_columns_fetch_task_uses_ingestion_recipe_and_running_status(self):
        from backend.services import columns_workflow

        request = object()

        with (
            patch(
                "backend.services.columns_workflow.launch_task_recipe",
                return_value={"task_id": "task-1", "message": columns_workflow.COLUMNS_FETCH_CREATED_MESSAGE},
            ) as launch,
            patch("backend.services.columns_workflow.update_task") as update_task,
        ):
            response = columns_workflow.create_columns_fetch_task("123", request)
            recipe = launch.call_args.args[0]
            recipe.on_created("task-1")

        self.assertEqual(
            {"success": True, "task_id": "task-1", "message": columns_workflow.COLUMNS_FETCH_CREATED_MESSAGE},
            response,
        )
        launch.assert_called_once()
        self.assertEqual("columns_fetch", recipe.task_type)
        self.assertEqual("采集专栏内容 (群组: 123)", recipe.description)
        self.assertEqual(columns_workflow.run_columns_fetch_task, recipe.task_func)
        self.assertEqual("123", recipe.ingestion_group_id)
        self.assertEqual((request,), recipe.args)
        self.assertEqual(columns_workflow.COLUMNS_FETCH_CREATED_MESSAGE, recipe.message)
        update_task.assert_called_once_with("task-1", "running", columns_workflow.COLUMNS_FETCH_RUNNING_MESSAGE)

if __name__ == "__main__":
    unittest.main()
