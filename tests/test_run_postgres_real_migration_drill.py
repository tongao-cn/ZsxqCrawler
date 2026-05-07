import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.run_postgres_real_migration_drill import run_drill


class RunPostgresRealMigrationDrillTests(unittest.TestCase):
    def test_run_drill_returns_two_when_no_sqlite_files_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("scripts.run_postgres_real_migration_drill.get_database_backend", return_value="postgres"),
                patch("scripts.run_postgres_real_migration_drill.get_postgres_dsn", return_value="postgresql://example"),
                redirect_stdout(StringIO()),
            ):
                code = run_drill(Path(tmp), Path(tmp) / "report.md")

        self.assertEqual(2, code)

    def test_run_drill_dry_run_does_not_execute_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.db").write_bytes(b"not opened during dry run")
            with (
                patch("scripts.run_postgres_real_migration_drill.get_database_backend", return_value="postgres"),
                patch("scripts.run_postgres_real_migration_drill.get_postgres_dsn", return_value="postgresql://example"),
                patch("scripts.run_postgres_real_migration_drill._run") as run_command,
                redirect_stdout(StringIO()),
            ):
                code = run_drill(root, root / "report.md", dry_run=True)

        self.assertEqual(0, code)
        run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
