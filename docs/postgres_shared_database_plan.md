# PostgreSQL Shared Database

ZsxqCrawler now uses PostgreSQL as the shared structured data source. Other
projects should read only from the stable `zsxq_public` schema.

## Recommended Layout

- Internal schemas: `zsxq_*`
  - Used by ZsxqCrawler internals.
  - Names may still be derived from compatibility path identifiers.
- Public read schema: `zsxq_public`
  - Stable interface for other projects.
  - Exposes views instead of internal tables.

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

## PostgreSQL Operations

Refresh public views and indexes:

```powershell
$env:ZSXQ_DATABASE_BACKEND = "postgres"
$env:ZSXQ_POSTGRES_DSN = "postgresql://zsxq_writer:password@host:5432/zsxq"
uv run manage-postgres-public-schema --apply --build-indexes
```

Inspect public schema SQL without applying it:

```powershell
uv run manage-postgres-public-schema
```

Production role initialization can be done with a privileged DSN:

```powershell
$env:ZSXQ_POSTGRES_DSN = "postgresql://postgres:admin-password@host:5432/zsxq"
uv run manage-postgres-public-schema --apply --build-indexes --login-roles --reader-password "<reader-password>" --writer-password "<writer-password>"
```

Generate a Markdown PostgreSQL status snapshot:

```powershell
uv run generate-postgres-status-report --output docs\postgres_status_report.md
```

Verify a reader DSN before giving it to another project:

```powershell
uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:password@host:5432/zsxq"
```

Run the repeatable Docker smoke after changing public view or permission code:

```powershell
.\scripts\run_postgres_shared_smoke.ps1
```

The smoke starts a disposable PostgreSQL container, creates representative
internal schemas directly in PostgreSQL, refreshes `zsxq_public`, checks
repeated refresh behavior, validates reader `SELECT`, and confirms the reader
cannot access internal schemas or create objects in the public schema.

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
back to the internal schema that produced them.

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
  details.

## Current Boundaries

- PostgreSQL is the only structured data source.
- The public schema is read-oriented. ZsxqCrawler remains the writer.
- Other projects should treat `zsxq_public` as the stable contract and should
  not depend on internal `zsxq_*` schemas.
- `--build-indexes` creates best-effort indexes on common internal query
  columns. It is safe to repeat and skips missing columns.
