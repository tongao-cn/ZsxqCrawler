import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


class DailyStockConceptRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_daily_stock_concept_route_error_preserves_status_and_detail_format(self):
        from backend.routes.daily_stock_concept_routes import _daily_stock_concept_route_error

        error = _daily_stock_concept_route_error("获取每日股票概念失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取每日股票概念失败: boom", error.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_stock_concept_task_metadata_preserves_fields(self):
        from backend.routes.daily_stock_concept_routes import _stock_concept_task_metadata

        self.assertEqual(
            {"group_id": "51111112855254", "report_date": "2026-06-13"},
            _stock_concept_task_metadata("51111112855254", "2026-06-13"),
        )
        self.assertEqual(
            {"group_id": "51111112855254", "report_date": None},
            _stock_concept_task_metadata("51111112855254", None),
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_create_daily_stock_concept_task_response_preserves_task_contract(self):
        from backend.routes.daily_stock_concept_routes import (
            TASK_CREATED_MESSAGE,
            DailyStockConceptRequest,
            _create_daily_stock_concept_task_response,
            run_daily_stock_concept_task,
        )

        request = DailyStockConceptRequest(date="2026-06-13", commentsPerTopic=3)

        with (
            patch("backend.routes.daily_stock_concept_routes.create_task", return_value="task-concept") as create_task,
            patch("backend.routes.daily_stock_concept_routes.enqueue_runtime_task") as enqueue_runtime_task,
        ):
            response = _create_daily_stock_concept_task_response("51111112855254", request)

        create_task.assert_called_once_with(
            "daily_stock_concepts",
            "提取每日股票概念 (群组: 51111112855254)",
            {"group_id": "51111112855254", "report_date": "2026-06-13"},
        )
        enqueue_runtime_task.assert_called_once_with(
            run_daily_stock_concept_task,
            "task-concept",
            "51111112855254",
            request,
        )
        self.assertEqual({"task_id": "task-concept", "message": TASK_CREATED_MESSAGE}, response)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_create_daily_stock_concepts_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import daily_stock_concept_routes

        request = daily_stock_concept_routes.DailyStockConceptRequest(date="2026-06-13")

        with patch.object(
            daily_stock_concept_routes,
            "_create_daily_stock_concept_task_response",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    daily_stock_concept_routes.create_daily_stock_concepts(
                        "group-1",
                        request,
                        FakeBackgroundTasks(),
                    )
                )

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("创建每日股票概念提取任务失败: boom", raised.exception.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_build_stock_concept_log_callback_writes_task_log(self):
        from backend.routes.daily_stock_concept_routes import _build_stock_concept_log_callback

        log_callback = _build_stock_concept_log_callback("task-1")

        with patch("backend.routes.daily_stock_concept_routes.add_task_log") as add_task_log:
            log_callback("hello")

        add_task_log.assert_called_once_with("task-1", "hello")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_extract_daily_stock_concepts_for_task_preserves_service_arguments(self):
        from backend.routes.daily_stock_concept_routes import (
            DailyStockConceptRequest,
            _extract_daily_stock_concepts_for_task,
        )

        request = DailyStockConceptRequest(date="2026-06-13", commentsPerTopic=2)
        expected = {"stocks": []}
        with (
            patch("backend.routes.daily_stock_concept_routes.extract_daily_stock_concepts", return_value=expected) as extract,
            patch("backend.routes.daily_stock_concept_routes.add_task_log") as add_task_log,
        ):
            result = _extract_daily_stock_concepts_for_task("task-1", "51111112855254", request)

            self.assertEqual(expected, result)
            extract.assert_called_once()
            call_args, call_kwargs = extract.call_args
            self.assertEqual(("51111112855254", "2026-06-13"), call_args)
            self.assertEqual(2, call_kwargs["comments_per_topic"])

            call_kwargs["log_callback"]("concept log")

        add_task_log.assert_called_once_with("task-1", "concept log")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_run_daily_stock_concept_task_uses_runtime_workflow_lifecycle(self):
        from backend.routes.daily_stock_concept_routes import DailyStockConceptRequest, run_daily_stock_concept_task

        request = DailyStockConceptRequest(date="2026-06-13", commentsPerTopic=2)
        with (
            patch("backend.routes.daily_stock_concept_routes.run_workflow") as run_workflow,
            patch(
                "backend.routes.daily_stock_concept_routes.extract_daily_stock_concepts",
                return_value={"stocks": []},
            ) as extract_daily_stock_concepts,
        ):
            run_daily_stock_concept_task("task-1", "51111112855254", request)

            run_workflow.assert_called_once()
            args, kwargs = run_workflow.call_args
            self.assertEqual(("task-1",), args)
            self.assertEqual("开始提取每日股票概念...", kwargs["running_message"])
            self.assertEqual("每日股票概念提取完成", kwargs["completed_message"])
            self.assertEqual("每日股票概念提取", kwargs["failure_label"])

            result = kwargs["work"]()
            self.assertEqual({"stocks": []}, result)
            extract_daily_stock_concepts.assert_called_once()
            call_args, call_kwargs = extract_daily_stock_concepts.call_args
            self.assertEqual(("51111112855254", "2026-06-13"), call_args)
            self.assertEqual(2, call_kwargs["comments_per_topic"])
            self.assertTrue(callable(call_kwargs["log_callback"]))

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_read_daily_stock_concepts_preserves_result_passthrough(self):
        import asyncio

        from backend.routes import daily_stock_concept_routes

        result_payload = {"date": "2026-06-13", "concepts": []}
        with patch.object(
            daily_stock_concept_routes,
            "get_daily_stock_concepts",
            return_value=result_payload,
        ) as get_concepts:
            result = asyncio.run(
                daily_stock_concept_routes.read_daily_stock_concepts(
                    "group-1",
                    "2026-06-13",
                )
            )

        self.assertEqual(result_payload, result)
        get_concepts.assert_called_once_with("group-1", "2026-06-13")

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_read_daily_stock_concepts_preserves_missing_result_404(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import daily_stock_concept_routes

        with patch.object(
            daily_stock_concept_routes,
            "get_daily_stock_concepts",
            return_value=None,
        ) as get_concepts:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    daily_stock_concept_routes.read_daily_stock_concepts("group-1", None)
                )

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("股票概念结果不存在，请先提取", raised.exception.detail)
        get_concepts.assert_called_once_with("group-1", None)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_read_daily_stock_concepts_preserves_wrapped_unexpected_error(self):
        import asyncio

        from fastapi import HTTPException

        from backend.routes import daily_stock_concept_routes

        with patch.object(
            daily_stock_concept_routes,
            "_daily_stock_concepts_or_404",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(daily_stock_concept_routes.read_daily_stock_concepts("group-1", None))

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("获取每日股票概念失败: boom", raised.exception.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_daily_stock_concepts_or_404_preserves_missing_result_404(self):
        from fastapi import HTTPException

        from backend.routes import daily_stock_concept_routes

        with patch.object(daily_stock_concept_routes, "get_daily_stock_concepts", return_value={}) as get_concepts:
            with self.assertRaises(HTTPException) as raised:
                daily_stock_concept_routes._daily_stock_concepts_or_404("group-1", "2026-06-13")

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("股票概念结果不存在，请先提取", raised.exception.detail)
        get_concepts.assert_called_once_with("group-1", "2026-06-13")


if __name__ == "__main__":
    unittest.main()
