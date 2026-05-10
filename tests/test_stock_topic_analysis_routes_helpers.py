import unittest
from importlib.util import find_spec
from unittest.mock import Mock, patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class StockTopicAnalysisRoutesHelperTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_stock_topic_matches_maps_value_error_to_400(self):
        from fastapi import HTTPException

        from backend.routes.stock_topic_analysis_routes import read_stock_topic_matches

        with patch(
            "backend.routes.stock_topic_analysis_routes.search_stock_topics",
            side_effect=ValueError("stock_name 不能为空"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await read_stock_topic_matches("51111112855254", "")

        self.assertEqual(400, raised.exception.status_code)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_create_stock_topic_analysis_enqueues_runtime_task(self):
        from backend.routes.stock_topic_analysis_routes import (
            StockTopicAnalysisRequest,
            create_stock_topic_analysis,
            run_stock_topic_analysis_task,
        )

        with (
            patch("backend.routes.stock_topic_analysis_routes.create_task", return_value="task-1") as create_task,
            patch("backend.routes.stock_topic_analysis_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            result = await create_stock_topic_analysis(
                "51111112855254",
                StockTopicAnalysisRequest(stockName="宁德时代"),
            )

        self.assertEqual("task-1", result["task_id"])
        create_task.assert_called_once()
        enqueue_runtime_task.assert_called_once_with(
            run_stock_topic_analysis_task,
            "task-1",
            "51111112855254",
            StockTopicAnalysisRequest(stockName="宁德时代"),
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_latest_stock_topic_analysis_raises_404_when_missing(self):
        from fastapi import HTTPException

        from backend.routes.stock_topic_analysis_routes import read_latest_stock_topic_analysis

        with patch("backend.routes.stock_topic_analysis_routes.get_latest_stock_topic_analysis", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                await read_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertEqual(404, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
