import unittest
from importlib.util import find_spec


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

        tasks_response = client.get("/api/tasks")
        self.assertEqual(200, tasks_response.status_code)
        self.assertIsInstance(tasks_response.json(), list)


if __name__ == "__main__":
    unittest.main()
