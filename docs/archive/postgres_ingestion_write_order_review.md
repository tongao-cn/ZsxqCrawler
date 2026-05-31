# PostgreSQL Ingestion Write Order Review

## Summary

This review closes the immediate P0/P1 follow-up after content child tables gained explicit unique semantics.

## Current Guardrails

- Runtime smoke now repeats topic/file imports and verifies child table uniqueness stays stable.
- `task_runtime.create_ingestion_task()` uses the shared `ingestion` lock key for crawl, file collection, download, and sync task types.
- `db_compat.py` no longer translates SQLite-only SQL, so new ingestion writes must be explicit PostgreSQL SQL.

## Write Order

Preferred shared-table order for ingestion paths:

1. `groups`
2. `users`
3. `topics`
4. content child tables such as `talks`, `questions`, `answers`, `articles`, `likes`, `latest_likes`, and emoji tables
5. file metadata tables
6. file/topic relation tables

`ZSXQDatabase.import_topic_data()` and `ZSXQFileDatabase.import_file_response()` now mostly follow this direction. The highest-risk shared tables are still `topics`, `files`, `topic_files`, and `file_topic_relations` because both topic ingestion and file ingestion can touch them.

## Likes Decision

`likes` remains an append/history table. It is now included in the content-table audit as read-only by `(topic_id, user_id, create_time)`, but the audit script does not delete from it or add schema constraints.

## Operational Check

If ingestion appears stuck after the first page, inspect PostgreSQL activity before debugging network/API paths:

```sql
SELECT pid, state, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN ('active', 'idle in transaction');
```

Treat `idle in transaction` or transaction lock waits around ingestion tasks as a database contention issue first.
