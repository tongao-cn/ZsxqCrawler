import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch


HAS_FASTAPI = find_spec("fastapi") is not None


class LocalGroupRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(HAS_FASTAPI, "FastAPI dependency is not installed")
    def test_scan_local_groups_finds_direct_and_database_dirs(self):
        from backend.core.local_group_runtime import scan_local_groups

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "123").mkdir()
            (base / "not-a-group").mkdir()
            (base / "databases" / "456").mkdir(parents=True)

            with patch("backend.core.local_group_runtime._collect_postgres_group_ids", return_value=set()):
                self.assertEqual({123, 456}, scan_local_groups(temp_dir, limit=10))

    @unittest.skipUnless(HAS_FASTAPI, "FastAPI dependency is not installed")
    def test_scan_local_groups_includes_postgres_groups(self):
        from backend.core.local_group_runtime import scan_local_groups

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("backend.core.local_group_runtime._collect_postgres_group_ids", return_value={789}):
                self.assertEqual({789}, scan_local_groups(temp_dir, limit=10))


if __name__ == "__main__":
    unittest.main()
