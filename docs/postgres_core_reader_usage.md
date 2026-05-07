# PostgreSQL Core Reader Usage

ZsxqCrawler stores structured data in PostgreSQL schema `zsxq_core`.
Other projects should connect with the read-only `zsxq_reader` role and query
`zsxq_core` tables directly.

## Reader DSN

Use a read-only DSN:

```text
postgresql://zsxq_reader:<password>@<host>:5432/<database>
```

Do not use the writer/admin DSN in downstream analysis projects.

## Common Tables

Recommended starting points:

- `zsxq_core.groups`: group metadata.
- `zsxq_core.topics`: topic records and counters.
- `zsxq_core.comments`: topic comments.
- `zsxq_core.files`: file metadata and download status.
- `zsxq_core.file_ai_analyses`: AI summaries for files.
- `zsxq_core.daily_ai_reports`: daily topic reports.
- `zsxq_core.accounts` and `zsxq_core.group_account_map`: account metadata, if the reader role is allowed to inspect account ownership.

## Example Queries

Recent topics:

```sql
SELECT group_id, topic_id, title, type, create_time
FROM zsxq_core.topics
WHERE group_id = 51111112855254
ORDER BY create_time DESC
LIMIT 50;
```

Downloaded files:

```sql
SELECT group_id, file_id, name, size, download_status, local_path, create_time
FROM zsxq_core.files
WHERE group_id = 51111112855254
ORDER BY create_time DESC
LIMIT 50;
```

File AI summaries:

```sql
SELECT f.group_id, f.file_id, f.name, a.status, a.summary, a.updated_at
FROM zsxq_core.files f
LEFT JOIN zsxq_core.file_ai_analyses a ON a.file_id = f.file_id
WHERE f.group_id = 51111112855254
ORDER BY f.create_time DESC
LIMIT 50;
```

## Access Rules

- `zsxq_reader` may `SELECT` from `zsxq_core`.
- `zsxq_reader` must not write, create tables, or manage schema objects.
- `zsxq_public` and legacy `zsxq_*` schemas are not part of the supported interface.
- Local `output/databases/{group_id}/downloads` and `images` directories contain resource files only; structured records are in PostgreSQL.

Before sharing a reader DSN, verify it:

```powershell
uv run verify-postgres-reader-access --dsn "<reader-dsn>"
```
