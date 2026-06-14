import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_DIAGNOSTICS_ROUTE_DEPS = find_spec("fastapi") is not None


class DiagnosticsRoutesHelperTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(HAS_DIAGNOSTICS_ROUTE_DEPS, "diagnostics route dependencies are not installed")
    async def test_diagnostics_route_error_preserves_status_and_detail_format(self):
        from backend.routes.diagnostics_routes import _diagnostics_route_error

        error = _diagnostics_route_error("获取 PostgreSQL 活动失败", RuntimeError("route boom"))

        self.assertEqual(500, error.status_code)
        self.assertEqual("获取 PostgreSQL 活动失败: route boom", error.detail)

    @unittest.skipUnless(HAS_DIAGNOSTICS_ROUTE_DEPS, "diagnostics route dependencies are not installed")
    async def test_get_postgres_activity_returns_service_payload(self):
        from backend.routes.diagnostics_routes import get_postgres_activity

        expected = [{"pid": 101, "state": "active"}]
        with patch(
            "backend.routes.diagnostics_routes.list_postgres_activity",
            return_value=expected,
        ) as list_activity:
            result = await get_postgres_activity(limit=5)

        self.assertEqual({"activity": expected}, result)
        list_activity.assert_called_once_with(limit=5)

    @unittest.skipUnless(HAS_DIAGNOSTICS_ROUTE_DEPS, "diagnostics route dependencies are not installed")
    async def test_get_postgres_activity_preserves_wrapped_unexpected_error(self):
        from fastapi import HTTPException

        from backend.routes.diagnostics_routes import get_postgres_activity

        with patch(
            "backend.routes.diagnostics_routes.list_postgres_activity",
            side_effect=RuntimeError("route boom"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await get_postgres_activity(limit=5)

        self.assertEqual(500, raised.exception.status_code)
        self.assertEqual("获取 PostgreSQL 活动失败: route boom", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
