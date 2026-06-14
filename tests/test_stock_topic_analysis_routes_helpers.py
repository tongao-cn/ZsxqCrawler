import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class StockTopicAnalysisRoutesHelperTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_create_stock_task_response_preserves_task_creation_contract(self):
        from backend.routes.stock_topic_analysis_routes import (
            TASK_CREATED_MESSAGE,
            StockQuestionRequest,
            _create_stock_task_response,
            run_stock_question_task,
        )

        request = StockQuestionRequest(question="固态电池怎么看")

        with (
            patch("backend.routes.stock_topic_analysis_routes.create_task", return_value="task-qa") as create_task,
            patch("backend.routes.stock_topic_analysis_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_stock_task_response(
                "stock_question_analysis",
                "A股问答 (群组: 51111112855254)",
                {"group_id": "51111112855254", "question": "固态电池怎么看"},
                run_stock_question_task,
                "51111112855254",
                request,
            )

        create_task.assert_called_once_with(
            "stock_question_analysis",
            "A股问答 (群组: 51111112855254)",
            {"group_id": "51111112855254", "question": "固态电池怎么看"},
        )
        enqueue_runtime_task.assert_called_once_with(
            run_stock_question_task,
            "task-qa",
            "51111112855254",
            request,
        )
        self.assertEqual({"task_id": "task-qa", "message": TASK_CREATED_MESSAGE}, response)

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
    async def test_run_stock_question_task_uses_runtime_workflow_lifecycle(self):
        from backend.routes.stock_topic_analysis_routes import StockQuestionRequest, run_stock_question_task

        request = StockQuestionRequest(question="固态电池怎么看")
        with (
            patch("backend.routes.stock_topic_analysis_routes.run_workflow") as run_workflow,
            patch(
                "backend.routes.stock_topic_analysis_routes.answer_stock_question",
                return_value={"answer": "ok"},
            ) as answer_stock_question,
            patch("backend.routes.stock_topic_analysis_routes.add_task_log") as add_task_log,
        ):
            run_stock_question_task("task-qa", "51111112855254", request)

            run_workflow.assert_called_once()
            args, kwargs = run_workflow.call_args
            self.assertEqual(("task-qa",), args)
            self.assertEqual("开始A股问答分析...", kwargs["running_message"])
            self.assertEqual("A股问答分析完成", kwargs["completed_message"])
            self.assertEqual("A股问答", kwargs["failure_label"])

            result = kwargs["work"]()
            self.assertEqual({"answer": "ok"}, result)
            add_task_log.assert_called_once_with("task-qa", "❓ 问题: 固态电池怎么看")
            answer_stock_question.assert_called_once()
            call_args, call_kwargs = answer_stock_question.call_args
            self.assertEqual(("51111112855254", "固态电池怎么看"), call_args)
            self.assertTrue(callable(call_kwargs["log_callback"]))

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_run_stock_topic_analysis_task_uses_runtime_workflow_lifecycle(self):
        from backend.routes.stock_topic_analysis_routes import StockTopicAnalysisRequest, run_stock_topic_analysis_task

        request = StockTopicAnalysisRequest(stockName="宁德时代")
        with (
            patch("backend.routes.stock_topic_analysis_routes.run_workflow") as run_workflow,
            patch(
                "backend.routes.stock_topic_analysis_routes.analyze_stock_topics",
                return_value={"summary": "ok"},
            ) as analyze_stock_topics,
            patch("backend.routes.stock_topic_analysis_routes.add_task_log") as add_task_log,
        ):
            run_stock_topic_analysis_task("task-1", "51111112855254", request)

            run_workflow.assert_called_once()
            args, kwargs = run_workflow.call_args
            self.assertEqual(("task-1",), args)
            self.assertEqual("开始个股话题分析...", kwargs["running_message"])
            self.assertEqual("个股话题分析完成", kwargs["completed_message"])
            self.assertEqual("个股话题分析", kwargs["failure_label"])

            result = kwargs["work"]()
            self.assertEqual({"summary": "ok"}, result)
            add_task_log.assert_called_once_with("task-1", "🔎 股票名称: 宁德时代")
            analyze_stock_topics.assert_called_once()
            call_args, call_kwargs = analyze_stock_topics.call_args
            self.assertEqual(("51111112855254", "宁德时代"), call_args)
            self.assertTrue(callable(call_kwargs["log_callback"]))

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_stock_topic_batch_completed_message_preserves_summary_defaults(self):
        from backend.routes.stock_topic_analysis_routes import _stock_topic_batch_completed_message

        self.assertEqual(
            "批量个股话题分析完成：成功 2，失败 1，无话题 3",
            _stock_topic_batch_completed_message({"summary": {"success": 2, "failed": 1, "no_topics": 3}}),
        )
        self.assertEqual(
            "批量个股话题分析完成：成功 2，失败 0，无话题 0",
            _stock_topic_batch_completed_message({"summary": {"success": 2}}),
        )
        self.assertEqual(
            "批量个股话题分析完成：成功 0，失败 0，无话题 0",
            _stock_topic_batch_completed_message({}),
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_stock_topic_batch_running_message_preserves_count_format(self):
        from backend.routes.stock_topic_analysis_routes import _stock_topic_batch_running_message

        self.assertEqual("开始批量个股话题分析，共 2 只股票...", _stock_topic_batch_running_message(2))
        self.assertEqual("开始批量个股话题分析，共 0 只股票...", _stock_topic_batch_running_message(0))

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_run_stock_topic_analysis_batch_task_uses_runtime_workflow_lifecycle(self):
        from backend.routes.stock_topic_analysis_routes import StockTopicAnalysisBatchRequest, run_stock_topic_analysis_batch_task

        request = StockTopicAnalysisBatchRequest(stockNames=["宁德时代", "德龙激光", "宁德时代"])
        events = []

        def parse_stock_names(stock_names):
            events.append(("parse", stock_names))
            return ["宁德时代", "德龙激光"]

        def analyze_stock_topics_batch(group_id, stock_names, *, log_callback):
            events.append(("analyze", group_id, stock_names, callable(log_callback)))
            log_callback("batch log")
            return {"summary": {"success": 2, "failed": 0, "no_topics": 0}}

        with (
            patch("backend.routes.stock_topic_analysis_routes.run_workflow") as run_workflow,
            patch("backend.routes.stock_topic_analysis_routes.parse_stock_names", side_effect=parse_stock_names),
            patch(
                "backend.routes.stock_topic_analysis_routes.analyze_stock_topics_batch",
                side_effect=analyze_stock_topics_batch,
            ),
            patch("backend.routes.stock_topic_analysis_routes.add_task_log") as add_task_log,
        ):
            run_stock_topic_analysis_batch_task("task-batch", "51111112855254", request)

            run_workflow.assert_called_once()
            args, kwargs = run_workflow.call_args
            self.assertEqual(("task-batch",), args)
            self.assertEqual("个股话题分析", kwargs["failure_label"])

            self.assertEqual("开始批量个股话题分析，共 2 只股票...", kwargs["running_message"]())
            result = kwargs["work"]()
            self.assertEqual(
                "批量个股话题分析完成：成功 2，失败 0，无话题 0",
                kwargs["completed_message"](result),
            )

        self.assertEqual(
            [
                ("parse", ["宁德时代", "德龙激光", "宁德时代"]),
                ("analyze", "51111112855254", ["宁德时代", "德龙激光"], True),
            ],
            events,
        )
        add_task_log.assert_called_once_with("task-batch", "batch log")

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
    async def test_read_latest_stock_topic_analysis_returns_service_result(self):
        from backend.routes.stock_topic_analysis_routes import read_latest_stock_topic_analysis

        expected = {"stock_name": "宁德时代", "status": "completed"}
        with patch(
            "backend.routes.stock_topic_analysis_routes.get_latest_stock_topic_analysis",
            return_value=expected,
        ) as get_latest:
            result = await read_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertEqual(expected, result)
        get_latest.assert_called_once_with("51111112855254", "宁德时代")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_read_latest_stock_topic_analysis_raises_404_when_missing(self):
        from fastapi import HTTPException

        from backend.routes.stock_topic_analysis_routes import read_latest_stock_topic_analysis

        with patch(
            "backend.routes.stock_topic_analysis_routes.get_latest_stock_topic_analysis",
            return_value=None,
        ) as get_latest:
            with self.assertRaises(HTTPException) as raised:
                await read_latest_stock_topic_analysis("51111112855254", "宁德时代")

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("个股话题分析结果不存在，请先分析", raised.exception.detail)
        get_latest.assert_called_once_with("51111112855254", "宁德时代")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_latest_stock_topic_analysis_or_404_preserves_missing_404(self):
        from fastapi import HTTPException

        from backend.routes import stock_topic_analysis_routes

        with patch(
            "backend.routes.stock_topic_analysis_routes.get_latest_stock_topic_analysis",
            return_value={},
        ) as get_latest:
            with self.assertRaises(HTTPException) as raised:
                stock_topic_analysis_routes._latest_stock_topic_analysis_or_404(
                    "51111112855254",
                    "宁德时代",
                )

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("个股话题分析结果不存在，请先分析", raised.exception.detail)
        get_latest.assert_called_once_with("51111112855254", "宁德时代")

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

    @unittest.skipUnless(HAS_ROUTE_DEPS, "stock topic analysis route dependencies are not installed")
    async def test_external_stock_summaries_preserves_default_report_date(self):
        from backend.routes import stock_topic_analysis_routes
        from backend.routes.stock_topic_analysis_routes import ExternalStockSummaryRequest

        expected = {"group_id": "51111112855254", "stocks": []}
        with patch(
            "backend.routes.stock_topic_analysis_routes.get_external_stock_summaries",
            return_value=expected,
        ) as service:
            result = stock_topic_analysis_routes._external_stock_summaries(
                "51111112855254",
                ExternalStockSummaryRequest(stockNames=["宁德时代"]),
            )

        self.assertEqual(expected, result)
        service.assert_called_once_with("51111112855254", ["宁德时代"], report_date=None)


if __name__ == "__main__":
    unittest.main()
