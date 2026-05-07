import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from backend.core.db_path_manager import DatabasePathManager


class DatabasePathManagerHelperTests(unittest.TestCase):
    def test_normalize_group_id_matches_existing_string_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)

            self.assertEqual(manager._normalize_group_id(12345), "12345")
            self.assertEqual(manager._normalize_group_id("00123"), "00123")

    def test_group_db_path_uses_normalized_group_dir_and_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)

            with redirect_stdout(StringIO()):
                db_path = manager._get_group_db_path(12345, "topics")

            self.assertEqual(
                db_path,
                os.path.join(temp_dir, "12345", "zsxq_topics_12345.db"),
            )
            self.assertTrue(os.path.isdir(os.path.join(temp_dir, "12345")))

    def test_config_db_path_stays_under_base_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DatabasePathManager(base_dir=temp_dir)

            self.assertEqual(
                manager._get_config_db_path(),
                os.path.join(temp_dir, "zsxq_config.db"),
            )


if __name__ == "__main__":
    unittest.main()
