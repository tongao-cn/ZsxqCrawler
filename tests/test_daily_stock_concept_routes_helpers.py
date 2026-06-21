import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class DailyStockConceptRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_daily_stock_concept_route_error_preserves_status_and_detail_format(self):
        from backend.routes.daily_stock_concept_routes import _daily_stock_concept_route_error

        error = _daily_stock_concept_route_error("获取每日股票概念失败", RuntimeError("boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取每日股票概念失败: boom", error.detail)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_daily_stock_concept_route_error_preserves_task_conflict_detail(self):
        from backend.routes.daily_stock_concept_routes import _daily_stock_concept_route_error
        from backend.services.task_launch import TaskLaunchConflict

        error = _daily_stock_concept_route_error(
            "创建每日股票概念提取任务失败",
            TaskLaunchConflict({"task_id": "task-old", "type": "crawl_all", "status": "running"}),
        )

        self.assertEqual(409, error.status_code)
        self.assertEqual(
            {
                "message": "该群组已有采集或同步任务正在运行",
                "task_id": "task-old",
                "type": "crawl_all",
                "status": "running",
            },
            error.detail,
        )

    @unittest.skipUnless(HAS_ROUTE_DEPS, "daily stock concept route dependencies are not installed")
    def test_create_daily_stock_concept_task_response_delegates_to_daily_workflow(self):
        from backend.routes.daily_stock_concept_routes import DailyStockConceptRequest, _create_daily_stock_concept_task_response

        request = DailyStockConceptRequest(date="2026-06-13", commentsPerTopic=3)

        with patch(
            "backend.routes.daily_stock_concept_routes.create_daily_stock_concept_task",
            return_value={"task_id": "task-concept", "message": "任务已创建，正在后台执行"},
        ) as create_task:
            response = _create_daily_stock_concept_task_response("51111112855254", request)

        create_task.assert_called_once_with(
            "51111112855254",
            date="2026-06-13",
            comments_per_topic=3,
        )
        self.assertEqual({"task_id": "task-concept", "message": "任务已创建，正在后台执行"}, response)

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
                    )
                )

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("创建每日股票概念提取任务失败: boom", raised.exception.detail)

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
                asyncio.run(daily_stock_concept_routes.read_daily_stock_concepts("group-1", None))

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


if __name__ == "__main__":
    unittest.main()
