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
uv run migrate-sqlite-to-postgres --root output\databases --replace-schema --build-public-views --build-indexes
```

Inspect public schema SQL without applying it:

```powershell
uv run manage-postgres-public-schema
```

Apply or refresh `zsxq_public` views and grants:

```powershell
uv run manage-postgres-public-schema --apply
```

Production role initialization can be done after the first migration with a
privileged DSN:

```powershell
$env:ZSXQ_POSTGRES_DSN = "postgresql://postgres:admin-password@host:5432/zsxq"
uv run manage-postgres-public-schema --apply --build-indexes --login-roles --reader-password "<reader-password>" --writer-password "<writer-password>"
```

After that, configure ZsxqCrawler with the writer DSN and share only the reader
DSN with other projects:

```toml
[database]
backend = "postgres"
postgres_dsn = "postgresql://zsxq_writer:<writer-password>@host:5432/zsxq"
```

Audit a real migration after loading data:

```powershell
$env:ZSXQ_DATABASE_BACKEND = "postgres"
$env:ZSXQ_POSTGRES_DSN = "postgresql://postgres:admin-password@host:5432/zsxq"
uv run audit-postgres-migration --root output\databases
```

Generate a Markdown migration status snapshot:

```powershell
uv run generate-postgres-migration-report --root output --output docs\postgres_real_migration_report.md
```

Run a complete real migration drill:

```powershell
uv run run-postgres-real-migration-drill --root output\databases --replace-schema
```

The drill stops before touching PostgreSQL if no `.db` files are found under
the root. Omit `--replace-schema` for a non-destructive import attempt, or pass
`--dry-run` to print the commands without executing them.

Verify a reader DSN before giving it to another project:

```powershell
uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:password@host:5432/zsxq"
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

- `zsxq_public.groups`: `group_id`, `group_name`, `group_type`,
  `background_url`, `created_at`, `source_updated_at`, `source_schema`.
- `zsxq_public.topics`: `group_id`, `topic_id`, `title`, `topic_type`,
  `create_time`, `updated_at`, `source_updated_at`, `source_schema`.
- `zsxq_public.comments`: `group_id`, `comment_id`, `topic_id`,
  `owner_user_id`, `text`, `create_time`, `source_updated_at`,
  `source_schema`.
- `zsxq_public.files`: `group_id`, `file_id`, `name`, `size`,
  `download_status`, `local_path`, `create_time`, `source_updated_at`,
  `source_schema`.
- `zsxq_public.columns`: `group_id`, `column_id`, `name`, `description`,
  `topics_count`, `created_at`, `source_updated_at`, `source_schema`.
- `zsxq_public.column_topics`: `group_id`, `column_id`, `topic_id`, `title`,
  `create_time`, `source_updated_at`, `source_schema`.
- `zsxq_public.daily_ai_reports`: `group_id`, `report_date`, `topic_count`,
  `summary`, `created_at`, `source_updated_at`, `source_schema`.
- `zsxq_public.file_ai_analyses`: `group_id`, `file_id`, `status`,
  `summary`, `content_type`, `source_path`, `source_updated_at`,
  `source_schema`.

Each view includes `source_schema` so downstream consumers can trace records
back to the compatibility schema that produced them.

`comments.group_id` is derived from the same schema's `topics` table when the
comment table itself does not carry `group_id`. `files.group_id` and
`file_ai_analyses.group_id` use a single-group fallback from the same schema's
`groups` table when present; otherwise they remain `NULL` until a stronger
file-to-topic/group relation is available.

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

Recommended onboarding checklist for another project:

- Receive only the `zsxq_reader` DSN.
- Run `uv run verify-postgres-reader-access --dsn "<reader-dsn>"` from this repo
  before sharing the DSN onward.
- Query only `zsxq_public.*` views.
- Do not depend on internal `zsxq_*` schema names; they are compatibility
  details derived from SQLite paths.

## Current Boundaries

- SQLite remains supported for local, zero-config usage.
- PostgreSQL is opt-in and recommended for shared analysis.
- The public schema is read-oriented. ZsxqCrawler remains the writer.
- The migration script does not delete PostgreSQL schemas unless
  `--replace-schema` is explicitly provided.
- Other projects should treat `zsxq_public` as the stable contract and should
  not depend on internal `zsxq_*` compatibility schemas.
- `--build-indexes` creates best-effort indexes on common internal query
  columns. It is safe to repeat and skips missing legacy columns.
