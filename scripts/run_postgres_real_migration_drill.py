from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from backend.storage.db_compat import get_database_backend, get_postgres_dsn
from scripts.migrate_sqlite_to_postgres import _iter_sqlite_files


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, check=True)


def _find_sqlite_files(root: Path) -> list[Path]:
    return list(_iter_sqlite_files(root)) if root.exists() else []


def run_drill(root: Path, report_path: Path, *, replace_schema: bool = False, dry_run: bool = False) -> int:
    if get_database_backend() != "postgres":
        raise RuntimeError("Set ZSXQ_DATABASE_BACKEND=postgres or config.toml [database].backend = 'postgres'")
    if not get_postgres_dsn():
        raise RuntimeError("PostgreSQL DSN is not configured")
    if not root.exists():
        raise FileNotFoundError(f"SQLite database root not found: {root}")

    sqlite_files = _find_sqlite_files(root)
    if not sqlite_files:
        print(f"No SQLite .db files found under {root}. Nothing was migrated.")
        print("Place source .db files under the root or pass --root to a directory that contains them.")
        return 2

    print(f"Found {len(sqlite_files)} SQLite database(s) under {root}:")
    for db_path in sqlite_files:
        print(f"- {db_path}")

    migrate_cmd = [
        "uv",
        "run",
        "migrate-sqlite-to-postgres",
        "--root",
        str(root),
        "--build-public-views",
        "--build-indexes",
    ]
    if replace_schema:
        migrate_cmd.append("--replace-schema")

    audit_cmd = ["uv", "run", "audit-postgres-migration", "--root", str(root)]
    report_cmd = [
        "uv",
        "run",
        "generate-postgres-migration-report",
        "--root",
        str(root),
        "--output",
        str(report_path),
    ]

    if dry_run:
        print("Dry run only. Planned commands:")
        for command in (migrate_cmd, audit_cmd, report_cmd):
            print("+ " + " ".join(command))
        return 0

    _run(migrate_cmd)
    _run(audit_cmd)
    _run(report_cmd)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real SQLite to PostgreSQL migration drill")
    parser.add_argument("--root", default=None, help="Directory containing .db files. Defaults to output/databases.")
    parser.add_argument(
        "--report",
        default="docs/postgres_real_migration_report.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--replace-schema",
        action="store_true",
        help="Drop each destination compatibility schema before importing. Use for full rehearsal only.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned commands without migrating.")
    args = parser.parse_args()

    project_root = _project_root()
    root = Path(args.root) if args.root else project_root / "output" / "databases"
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = project_root / report_path

    raise SystemExit(run_drill(root, report_path, replace_schema=args.replace_schema, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
