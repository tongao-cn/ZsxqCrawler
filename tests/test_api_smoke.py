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
            patch("backend.routes.group_routes.build_account_group_detection", return_value={}),
            patch("backend.routes.group_routes.get_cached_local_group_ids", return_value=set()),
            patch("backend.routes.group_routes.get_primary_cookie", return_value="cookie"),
            patch("backend.routes.group_routes.fetch_groups_from_api", side_effect=RuntimeError("boom")),
        ):
            response = TestClient(create_app()).get("/api/groups")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"groups": [], "total": 0}, response.json())

    @unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI test dependencies are not installed")
    def test_clear_topic_database_logging_is_gbk_safe(self):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        class FakePathManager:
            def get_topics_db_path(self, group_id):
                return r"C:\tmp\missing-topic-db.sqlite"

        def gbk_print(*args, **kwargs):
            " ".join(str(arg) for arg in args).encode("gbk")

        with (
            patch("backend.routes.topic_routes.get_db_path_manager", return_value=FakePathManager()),
            patch("backend.routes.topic_routes.os.path.exists", return_value=False),
            patch("builtins.print", side_effect=gbk_print),
        ):
            response = TestClient(create_app()).post("/api/topics/clear/group-1")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"message": "群组 group-1 的话题数据库不存在"}, response.json())

    @unittest.skipUnless(HAS_API_TEST_DEPS, "FastAPI test dependencies are not installed")
    def test_clear_file_database_logging_is_gbk_safe(self):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        def gbk_print(*args, **kwargs):
            " ".join(str(arg) for arg in args).encode("gbk")

        with (
            patch("backend.routes.file_routes._get_files_db_path", return_value=r"C:\tmp\missing-files-db.sqlite"),
            patch("backend.routes.file_routes.os.path.exists", return_value=False),
            patch("builtins.print", side_effect=gbk_print),
        ):
            response = TestClient(create_app()).post("/api/files/clear/group-1")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"message": "群组 group-1 的文件数据库不存在"}, response.json())


if __name__ == "__main__":
    unittest.main()
