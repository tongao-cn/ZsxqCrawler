import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.verify_postgres_writer_access import WriterCheck, print_checks


class VerifyPostgresWriterAccessTests(unittest.TestCase):
    def test_print_checks_returns_success_when_all_pass(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(0, print_checks([WriterCheck("core", True, "ok")]))

    def test_print_checks_returns_failure_when_any_fail(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(1, print_checks([WriterCheck("core", True, "ok"), WriterCheck("legacy", False, "bad")]))


if __name__ == "__main__":
    unittest.main()
