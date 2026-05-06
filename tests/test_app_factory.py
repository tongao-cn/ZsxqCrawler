import unittest
from importlib.util import find_spec


HAS_APP_DEPS = find_spec("fastapi") is not None and find_spec("loguru") is not None


class AppFactoryTests(unittest.TestCase):
    @unittest.skipUnless(HAS_APP_DEPS, "FastAPI app dependencies are not installed")
    def test_create_app_registers_core_routes(self):
        from backend.main import create_app

        app = create_app()
        paths = {route.path for route in app.routes}

        self.assertEqual("知识星球数据采集器 API", app.title)
        self.assertIn("/api/health", paths)
        self.assertIn("/api/tasks/{task_id}", paths)
        self.assertIn("/api/crawl/latest-until-complete/{group_id}", paths)


if __name__ == "__main__":
    unittest.main()
