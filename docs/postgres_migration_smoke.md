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
