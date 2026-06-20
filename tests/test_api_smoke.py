import unittest
from importlib.util import find_spec
from unittest.mock import patch

from backend.storage.db_compat import get_postgres_dsn


HAS_API_TEST_DEPS = (
    find_spec("fastapi") is not None
    and find_spec("loguru") is not None
    and find_spec("httpx") is not None
)


class ApiSmokeTests(unittest.TestCase):
    @unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI test dependencies are not installed")
    def test_core_endpoints_respond(self):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        client = TestClient(create_app())

        root_response = client.get("/")
        self.assertEqual(200, root_response.status_code)
        self.assertEqual("知识星球数据采集器 API 服务", root_response.json()["message"])

        health_response = client.get("/api/health")
        self.assertEqual(200, health_response.status_code)
        self.assertEqual("healthy", health_response.json()["status"])

        if not get_postgres_dsn():
            return

        tasks_response = client.get("/api/tasks")
        self.assertEqual(200, tasks_response.status_code)
        self.assertIsInstance(tasks_response.json(), list)

    @unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI test dependencies are not installed")
    def test_groups_endpoint_falls_back_when_remote_groups_fail(self):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        with (
            patch("backend.services.group_workflow_service.build_account_group_detection", return_value={}),
            patch("backend.services.group_workflow_service.get_cached_local_group_ids", return_value=set()),
            patch("backend.services.group_workflow_service.fetch_official_groups", side_effect=RuntimeError("boom")),
        ):
            response = TestClient(create_app()).get("/api/groups")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"groups": [], "total": 0}, response.json())

    @unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI test dependencies are not installed")
    def test_clear_topic_database_logging_is_gbk_safe(self):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        def gbk_print(*args, **kwargs):
            " ".join(str(arg) for arg in args).encode("gbk")

        with (
            patch("backend.services.topic_local_service._clear_group_topic_data", return_value={"topics": 0}),
            patch("builtins.print", side_effect=gbk_print),
        ):
            response = TestClient(create_app()).post("/api/topics/clear/group-1")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"message": "群组 group-1 的话题数据和图片缓存已删除", "deleted": {"topics": 0}},
            response.json(),
        )

    @unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI test dependencies are not installed")
    def test_clear_file_database_logging_is_gbk_safe(self):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        def gbk_print(*args, **kwargs):
            " ".join(str(arg) for arg in args).encode("gbk")

        with (
            patch(
                "backend.routes.file_routes.clear_file_database_response",
                return_value={"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 0}},
            ),
            patch("builtins.print", side_effect=gbk_print),
        ):
            response = TestClient(create_app()).post("/api/files/clear/group-1")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"message": "群组 group-1 的文件数据和图片缓存已删除", "deleted": {"files": 0}},
            response.json(),
        )


if __name__ == "__main__":
    unittest.main()
