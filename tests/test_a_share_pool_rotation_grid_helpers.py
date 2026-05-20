import unittest

from scripts.run_a_share_pool_rotation_grid import _parse_bucket


class ASharePoolRotationGridHelperTests(unittest.TestCase):
    def test_parse_bucket_supports_all_bucket(self):
        self.assertEqual(("topn", "all", 1, 1_000_000), _parse_bucket("all"))


if __name__ == "__main__":
    unittest.main()
