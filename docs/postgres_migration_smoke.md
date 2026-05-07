# PostgreSQL Migration Smoke

Date: 2026-05-07

This smoke test used a temporary Docker PostgreSQL container and a throwaway
SQLite fixture under `tmp/pg_smoke`. The fixture included:

- a normal `topics` table with a boolean column
- an autoincrement `crawl_log` table
- a quoted table name with quoted column names containing spaces

Commands verified:

```powershell
docker run --name zsxq-pg-smoke `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_DB=zsxq_smoke `
  -p 55432:5432 `
  -d postgres:16-alpine

$env:ZSXQ_DATABASE_BACKEND='postgres'
$env:ZSXQ_POSTGRES_DSN='postgresql://postgres:postgres@localhost:55432/zsxq_smoke'
uv run migrate-sqlite-to-postgres --root tmp\pg_smoke --replace-schema
```

Observed migration result:

```text
tmp\pg_smoke\quoted-db.db -> schema zsxq_quoted_db_2caf1ee1: 3 tables, 3 rows
```

PostgreSQL checks confirmed:

- destination schema contained `crawl_log`, `topics`, and `weird table`
- `topics.active` migrated from SQLite boolean-like integer to PostgreSQL boolean
- `crawl_log.id` autoincrement data migrated
- quoted table and column names with spaces were queryable

The temporary Docker container and `tmp/pg_smoke` fixture were removed after the
smoke test.

Repeatable shared-schema smoke:

```powershell
.\scripts\run_postgres_shared_smoke.ps1
```

Expected additional checks:

- `zsxq_public` exposes all first-stage views
- `zsxq_public.topics`, `zsxq_public.files`, and `zsxq_public.groups` return
  fixture rows from multiple migrated SQLite databases
- legacy/minimal databases produce `NULL` optional public fields instead of
  invalid view SQL
- `comments.group_id` can be filled from the migrated `topics` table
- internal table indexes can be created repeatedly
- migration row counts and public view row counts pass `audit-postgres-migration`
- a reader role can `SELECT` from public views but cannot write to them
- a reader role cannot read internal `zsxq_*` compatibility schemas
- repeated `--build-public-views` runs do not fail

Shared-schema smoke on 2026-05-07 confirmed:

- `uv run migrate-sqlite-to-postgres --root tmp\pg_shared_smoke --replace-schema --build-public-views`
  migrated 8 tables and 8 rows into `zsxq_shared_0d48c966`
- `zsxq_public` exposed 8 views
- `zsxq_public.topics`, `zsxq_public.files`, and `zsxq_public.groups` returned fixture rows
- `zsxq_reader` could `SELECT` from public views
- write attempts through `zsxq_reader` failed
- repeated `uv run migrate-sqlite-to-postgres --build-public-views` refreshed views without re-importing SQLite files

The scripted smoke extends this manual check by creating both a full fixture and
a legacy/minimal fixture, then validating reader isolation from internal schemas.
