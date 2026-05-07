# PostgreSQL Legacy Schema Drop Plan

This is the physical deletion plan for old path-derived `zsxq_*` schemas after
the fixed `zsxq_core` cutover. It is intentionally separate from the migration
and archive report; no command in the normal migration flow deletes schemas.

## Current Deletion Gate

Deletion is allowed only when all of these checks pass on the target database:

- `generate-postgres-legacy-archive-report` reports `Held schema count: 0`.
- `Untracked legacy row count` is `0`.
- `Ready-to-drop schema count` equals the current legacy schema count.
- `migrate-postgres-schemas-to-core --verify-only` passes.
- `zsxq_public` row counts do not regress after `manage-postgres-public-schema`.
- A fresh database backup exists and has been restore-tested or otherwise
  validated by the database operator.
- The application has already been running with new writes going only to
  `zsxq_core`, and legacy schema count stays unchanged after a real crawl/task
  write probe.

The current real archive report shows all legacy rows are tracked by
`zsxq_core.record_sources`, but this document still treats deletion as a manual
operator action.

## Pre-Delete Checklist

Run these commands immediately before producing the final drop SQL:

```powershell
$env:ZSXQ_DATABASE_BACKEND = "postgres"
$env:ZSXQ_POSTGRES_DSN = "postgresql://zsxq_writer:password@host:5432/zsxq"

uv run migrate-postgres-schemas-to-core --apply
uv run backfill-postgres-core-group-ids --apply
uv run manage-postgres-public-schema --apply --build-indexes
uv run migrate-postgres-schemas-to-core --verify-only
uv run generate-postgres-status-report --output docs\postgres_status_report.md
uv run generate-postgres-legacy-archive-report --output docs\postgres_legacy_archive_report.md
```

Then inspect `docs\postgres_legacy_archive_report.md` and confirm:

- The `Drop Readiness` table has no `hold_untracked_rows`.
- The `Held Schemas` table is empty.
- The generated `DROP SCHEMA` statements include only schemas marked
  `ready_to_drop_empty` or `ready_to_drop_tracked`.

## Execution Shape

Use a privileged maintenance connection, not the normal reader DSN. Prefer a
single explicit maintenance window:

1. Pause crawls, file analysis jobs, and scheduled task writers.
2. Take a database backup.
3. Regenerate `docs\postgres_legacy_archive_report.md`.
4. Copy only the generated `DROP SCHEMA ... CASCADE;` block from the report into
   a reviewed SQL file.
5. Execute the SQL inside one transaction where the PostgreSQL environment
   permits it.
6. Re-run public schema refresh and status verification.
7. Resume writers only after checks pass.

Suggested verification after deletion:

```powershell
uv run manage-postgres-public-schema --apply --build-indexes
uv run migrate-postgres-schemas-to-core --verify-only
uv run generate-postgres-status-report --output docs\postgres_status_report.md
uv run generate-postgres-legacy-archive-report --output docs\postgres_legacy_archive_report.md
uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:password@host:5432/zsxq"
uv run verify-postgres-writer-access --dsn "postgresql://zsxq_writer:password@host:5432/zsxq"
```

After deletion, the expected archive report should show:

- `Legacy schema count: 0`
- `Legacy row count: 0`
- `Ready-to-drop schema count: 0`
- `Held schema count: 0`

## Rollback Boundary

Once legacy schemas are dropped, rollback means restoring the database backup.
The migration code can recreate `zsxq_core` and `zsxq_public`, but it cannot
recreate deleted legacy schemas without a backup.

Because `zsxq_public` reads from `zsxq_core`, downstream reader projects should
not need any code change when legacy schemas are deleted.

