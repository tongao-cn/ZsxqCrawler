import asyncio
import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class ResearchRadarRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "research radar route dependencies are not installed")
    def test_create_research_radar_task_response_delegates_to_workflow(self):
        from backend.routes.research_radar_routes import ResearchRadarRequest, _create_research_radar_task_response

        request = ResearchRadarRequest(date="2026-06-26", commentsPerTopic=5)

        with patch(
            "backend.routes.research_radar_routes.create_research_radar_task",
            return_value={"task_id": "task-radar", "message": "任务已创建，正在后台执行"},
        ) as create_task:
            response = _create_research_radar_task_response("303", request)

        create_task.assert_called_once_with("303", date="2026-06-26", comments_per_topic=5)
        self.assertEqual({"task_id": "task-radar", "message": "任务已创建，正在后台执行"}, response)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "research radar route dependencies are not installed")
    def test_read_research_radar_or_404_raises_for_missing_result(self):
        from fastapi import HTTPException
        from backend.routes import research_radar_routes

        with patch.object(research_radar_routes, "get_research_radar", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                research_radar_routes._research_radar_or_404("303", "2026-06-26")

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("研究雷达结果不存在，请先生成", raised.exception.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "research radar route dependencies are not installed")
    def test_create_research_radar_maps_bad_date_to_400(self):
        from fastapi import HTTPException
        from backend.routes import research_radar_routes

        request = research_radar_routes.ResearchRadarRequest(date="bad-date")

        with patch.object(
            research_radar_routes,
            "create_research_radar_task",
            side_effect=ValueError("date 必须是 YYYY-MM-DD 格式"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(research_radar_routes.create_research_radar("303", request))

        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual("date 必须是 YYYY-MM-DD 格式", raised.exception.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "research radar route dependencies are not installed")
    def test_read_research_radar_maps_bad_date_to_400(self):
        from fastapi import HTTPException
        from backend.routes import research_radar_routes

        with patch.object(
            research_radar_routes,
            "get_research_radar",
            side_effect=ValueError("date 必须是 YYYY-MM-DD 格式"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(research_radar_routes.read_research_radar("303", date="bad-date"))

        self.assertEqual(400, raised.exception.status_code)
        self.assertEqual("date 必须是 YYYY-MM-DD 格式", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
