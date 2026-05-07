import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from backend.core.db_path_manager import DatabasePathManager


class DatabasePathManagerHelperTests(unittest.TestCase):
    def test_normalize_group_id_matches_existing_string_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)

            self.assertEqual(manager._normalize_group_id(12345), "12345")
            self.assertEqual(manager._normalize_group_id("00123"), "00123")

    def test_group_dir_uses_normalized_group_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)

            with redirect_stdout(StringIO()):
                group_dir = manager.get_group_dir(12345)

            self.assertEqual(
                group_dir,
                os.path.join(temp_dir, "12345"),
            )
            self.assertTrue(os.path.isdir(os.path.join(temp_dir, "12345")))

    def test_group_data_dir_returns_path_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)

            self.assertEqual(manager.get_group_data_dir("12345"), Path(temp_dir) / "12345")

    def test_list_all_groups_returns_local_resource_dirs_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)
            os.makedirs(os.path.join(temp_dir, "12345"))
            os.makedirs(os.path.join(temp_dir, "not-a-group"))

            self.assertEqual(
                manager.list_all_groups(),
                [{"group_id": "12345", "group_dir": os.path.join(temp_dir, "12345")}],
            )


if __name__ == "__main__":
    unittest.main()
