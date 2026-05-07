# PostgreSQL Shared Database

ZsxqCrawler supports a gradual PostgreSQL migration. SQLite remains the default
local mode, while PostgreSQL is the recommended mode for shared analysis and
service-style deployments.

## Recommended Layout

- Internal compatibility schemas: `zsxq_*`
  - Created from each original SQLite `.db` path.
  - Used by ZsxqCrawler internals and migration compatibility.
- Public read schema: `zsxq_public`
  - Stable interface for other projects.
  - Exposes views instead of internal compatibility tables.

## Connection Roles

Recommended writer DSN for ZsxqCrawler:

```toml
[database]
backend = "postgres"
postgres_dsn = "postgresql://zsxq_writer:password@host:5432/zsxq"
```

Recommended reader DSN for other projects:

```text
postgresql://zsxq_reader:password@host:5432/zsxq
```

The reader role is intended to have only:

- `USAGE` on schema `zsxq_public`
- `SELECT` on public views

It should not write to internal `zsxq_*` schemas.

## Migration Commands

Migrate existing SQLite data into PostgreSQL compatibility schemas:

```powershell
$env:ZSXQ_DATABASE_BACKEND = "postgres"
$env:ZSXQ_POSTGRES_DSN = "postgresql://zsxq_writer:password@host:5432/zsxq"
uv run migrate-sqlite-to-postgres --root output\databases --replace-schema
```

Refresh public views in the same step:

```powershell
uv run migrate-sqlite-to-postgres --root output\databases --replace-schema --build-public-views
```

Inspect public schema SQL without applying it:

```powershell
uv run manage-postgres-public-schema
```

Apply or refresh `zsxq_public` views and grants:

```powershell
uv run manage-postgres-public-schema --apply
```

Run the repeatable Docker smoke after changing migration or public view code:

```powershell
.\scripts\run_postgres_shared_smoke.ps1
```

The smoke creates two temporary SQLite fixtures:

- `shared-full.db`, with all first-stage public view tables and optional time
  fields.
- `legacy-minimal.db`, with only required `groups`, `topics`, and `files`
  fields to verify old databases still build public views with `NULL` optional
  columns.

It then starts a disposable PostgreSQL container, migrates both fixtures,
refreshes `zsxq_public`, checks repeated refresh behavior, validates reader
`SELECT`, and confirms the reader cannot access internal schemas or create
objects in the public schema.

## Public Views

Initial shared views:

- `zsxq_public.groups`
- `zsxq_public.topics`
- `zsxq_public.comments`
- `zsxq_public.files`
- `zsxq_public.columns`
- `zsxq_public.column_topics`
- `zsxq_public.daily_ai_reports`
- `zsxq_public.file_ai_analyses`

Each view includes `source_schema` so downstream consumers can trace records
back to the compatibility schema that produced them.

Minimum Python read example for other projects:

```python
import psycopg2

dsn = "postgresql://zsxq_reader:password@host:5432/zsxq"
with psycopg2.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT group_id, topic_id, title, create_time, source_schema
            FROM zsxq_public.topics
            ORDER BY create_time DESC NULLS LAST
            LIMIT 20
            """
        )
        rows = cur.fetchall()
```

Minimum SQL read example:

```sql
SELECT file_id, name, download_status, local_path, source_schema
FROM zsxq_public.files
WHERE download_status = 'downloaded';
```

## Current Boundaries

- SQLite remains supported for local, zero-config usage.
- PostgreSQL is opt-in and recommended for shared analysis.
- The public schema is read-oriented. ZsxqCrawler remains the writer.
- The migration script does not delete PostgreSQL schemas unless
  `--replace-schema` is explicitly provided.
- Other projects should treat `zsxq_public` as the stable contract and should
  not depend on internal `zsxq_*` compatibility schemas.
