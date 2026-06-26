import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch


class ResearchRadarWorkflowTests(unittest.TestCase):
    def test_generate_research_radar_uses_existing_sources_and_saves_run(self):
        from backend.services import research_radar_workflow as workflow

        conn = Mock()
        material = SimpleNamespace(
            topics=[{"topic_id": "101", "title": "PCB", "talk_text": "PCB涨价"}],
            topic_count=1,
        )
        current_rows = [{"topic_id": "101", "stock_name": "沪电股份", "concepts": ["PCB"], "confidence": 0.8}]
        baseline_rows = [{"topic_id": "90", "stock_name": "旧股票", "concepts": ["机器人"], "confidence": 0.6}]
        candidates = [{"candidate_id": "direction:PCB", "direction": "PCB", "title": "PCB", "summary": "PCB", "evidence": []}]

        with (
            patch.object(workflow, "connect_topic_material_db", return_value=conn),
            patch.object(workflow, "load_daily_topic_material", return_value=material) as load_material,
            patch.object(workflow, "load_topic_stock_extractions", side_effect=[current_rows, baseline_rows]) as load_rows,
            patch.object(workflow, "build_research_radar_candidates", return_value=candidates) as build_candidates,
            patch.object(workflow, "summarize_radar_candidates", return_value=(candidates, "model-a")) as summarize,
            patch.object(workflow, "save_research_radar_run", return_value=12) as save_run,
        ):
            result = workflow.generate_research_radar("303", "2026-06-26", task_id="task-1")

        load_material.assert_called_once_with("303", report_date=date(2026, 6, 26), comments_per_topic=8)
        self.assertEqual(2, load_rows.call_count)
        build_candidates.assert_called_once()
        summarize.assert_called_once_with(candidates, report_date="2026-06-26")
        save_run.assert_called_once()
        conn.close.assert_called_once_with()
        self.assertEqual(12, result["run_id"])
        self.assertEqual(1, result["logic_count"])

    def test_create_research_radar_task_uses_task_launch_recipe(self):
        from backend.services import research_radar_workflow as workflow

        with patch.object(
            workflow,
            "launch_task_recipe",
            return_value={"task_id": "task-radar", "message": "任务已创建，正在后台执行"},
        ) as launch:
            response = workflow.create_research_radar_task("303", date="2026-06-26", comments_per_topic=5)

        self.assertEqual({"task_id": "task-radar", "message": "任务已创建，正在后台执行"}, response)
        recipe = launch.call_args.args[0]
        self.assertEqual("research_radar", recipe.task_type)
        self.assertEqual("303", recipe.group_id)
        self.assertEqual(("303", recipe.args[1]), recipe.args)
        self.assertEqual("2026-06-26", recipe.metadata["report_date"])


if __name__ == "__main__":
    unittest.main()
