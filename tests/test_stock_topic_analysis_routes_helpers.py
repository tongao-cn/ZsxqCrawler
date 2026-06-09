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
    async def test_extract_stock_topics_from_image_calls_service(self):
        from backend.routes.stock_topic_analysis_routes import StockTopicImageExtractRequest, extract_stock_topics_from_image

        expected = {"stockNames": ["宁德时代"], "model": "test-model"}
        with patch("backend.routes.stock_topic_analysis_routes.extract_stock_names_from_image", return_value=expected) as service:
            result = await extract_stock_topics_from_image(StockTopicImageExtractRequest(imageDataUrl="data:image/png;base64,aW1n"))

        self.assertEqual(expected, result)
        service.assert_called_once_with("data:image/png;base64,aW1n")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_stock_question_matches_maps_value_error_to_400(self):
        from fastapi import HTTPException

        from backend.routes.stock_topic_analysis_routes import read_stock_question_matches

        with patch(
            "backend.routes.stock_topic_analysis_routes.search_stock_question_topics",
            side_effect=ValueError("question 不能为空"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await read_stock_question_matches("51111112855254", "")

        self.assertEqual(400, raised.exception.status_code)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_create_stock_question_analysis_enqueues_runtime_task(self):
        from backend.routes.stock_topic_analysis_routes import (
            StockQuestionRequest,
            create_stock_question_analysis,
            run_stock_question_task,
        )

        with (
            patch("backend.routes.stock_topic_analysis_routes.create_task", return_value="task-qa") as create_task,
            patch("backend.routes.stock_topic_analysis_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            result = await create_stock_question_analysis(
                "51111112855254",
                StockQuestionRequest(question="固态电池怎么看"),
            )

        self.assertEqual("task-qa", result["task_id"])
        self.assertEqual("stock_question_analysis", create_task.call_args.args[0])
        enqueue_runtime_task.assert_called_once_with(
            run_stock_question_task,
            "task-qa",
            "51111112855254",
            StockQuestionRequest(question="固态电池怎么看"),
        )

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
    async def test_create_stock_topic_analysis_batch_enqueues_runtime_task(self):
        from backend.routes.stock_topic_analysis_routes import (
            StockTopicAnalysisBatchRequest,
            create_stock_topic_analysis_batch,
            run_stock_topic_analysis_batch_task,
        )

        with (
            patch("backend.routes.stock_topic_analysis_routes.create_task", return_value="task-2") as create_task,
            patch("backend.routes.stock_topic_analysis_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            result = await create_stock_topic_analysis_batch(
                "51111112855254",
                StockTopicAnalysisBatchRequest(stockNames=["宁德时代", "德龙激光", "宁德时代"]),
            )

        self.assertEqual("task-2", result["task_id"])
        create_task.assert_called_once()
        self.assertEqual("stock_topic_analysis_batch", create_task.call_args.args[0])
        enqueue_runtime_task.assert_called_once_with(
            run_stock_topic_analysis_batch_task,
            "task-2",
            "51111112855254",
            StockTopicAnalysisBatchRequest(stockNames=["宁德时代", "德龙激光"]),
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_latest_stock_topic_analysis_raises_404_when_missing(self):
        from fastapi import HTTPException

        from backend.routes.stock_topic_analysis_routes import read_latest_stock_topic_analysis

        with patch("backend.routes.stock_topic_analysis_routes.get_latest_stock_topic_analysis", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                await read_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertEqual(404, raised.exception.status_code)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_latest_stock_topic_analyses_returns_mixed_rows(self):
        from backend.routes.stock_topic_analysis_routes import read_latest_stock_topic_analyses

        expected = {
            "group_id": "51111112855254",
            "stocks": [
                {"stock_name": "宁德时代", "status": "completed"},
                {"stock_name": "德龙激光", "status": "missing"},
            ],
        }
        with patch("backend.routes.stock_topic_analysis_routes.get_latest_stock_topic_analyses", return_value=expected):
            result = await read_latest_stock_topic_analyses("51111112855254", "宁德时代、德龙激光")

        self.assertEqual(expected, result)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_external_stock_summaries_calls_service(self):
        from backend.routes.stock_topic_analysis_routes import (
            ExternalStockSummaryRequest,
            read_external_stock_summaries,
        )

        expected = {
            "group_id": "51111112855254",
            "report_date": "2026-06-09",
            "stocks": [{"stock_name": "宁德时代", "concepts": ["储能"], "summary_markdown": "summary"}],
        }
        with patch("backend.routes.stock_topic_analysis_routes.get_external_stock_summaries", return_value=expected) as service:
            result = await read_external_stock_summaries(
                "51111112855254",
                ExternalStockSummaryRequest(stockNames=["宁德时代"], date="2026-06-09"),
            )

        self.assertEqual(expected, result)
        service.assert_called_once_with("51111112855254", ["宁德时代"], report_date="2026-06-09")


if __name__ == "__main__":
    unittest.main()
