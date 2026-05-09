import unittest
from unittest.mock import mock_open, patch


class AppConfigHelperTests(unittest.TestCase):
    def test_load_config_reads_first_existing_config_path(self):
        from backend.core import app_config

        config_content = b'[auth]\ncookie = "cookie-1"\ngroup_id = "group-1"\n'

        with (
            patch("backend.core.app_config.os.path.exists", side_effect=lambda path: path == "../config.toml"),
            patch("builtins.open", mock_open(read_data=config_content)) as opened,
        ):
            config = app_config.load_config()

        opened.assert_called_once_with("../config.toml", "rb")
        self.assertEqual("cookie-1", config["auth"]["cookie"])
        self.assertEqual("group-1", config["auth"]["group_id"])


if __name__ == "__main__":
    unittest.main()
