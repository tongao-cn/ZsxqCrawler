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
- `zsxq_core.zsxq_a_share_daily_mentions`: group-scoped A-share recommendation-pool mention counts.
- `zsxq_core.zsxq_a_share_topic_stock_extractions`: topic-level stock, concept, reason, and confidence extraction evidence.
- `zsxq_core.daily_stock_concepts`: same-day stock-concept summaries derived from group topics.
- `zsxq_core.stock_topic_analyses`: latest saved per-stock topic summaries.
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

A-share recommendation-pool rows:

```sql
SELECT group_id, mention_date, company, mentions_count, updated_at
FROM zsxq_core.zsxq_a_share_daily_mentions
WHERE group_id = '51111112855254'
ORDER BY mention_date DESC, mentions_count DESC
LIMIT 100;
```

Topic-level A-share evidence:

```sql
SELECT group_id, topic_date, topic_id, stock_name, stock_code, market,
       concepts_json, reason, confidence
FROM zsxq_core.zsxq_a_share_topic_stock_extractions
WHERE group_id = '51111112855254'
ORDER BY topic_date DESC, stock_name ASC
LIMIT 100;
```

## A-share Research Dataset Export

For downstream stock research, export a daily stock-signal CSV:

```powershell
uv run export-a-share-research-dataset --group-id 51111112855254 --start-date 2026-05-01 --end-date 2026-05-12 --output output\a_share_research\51111112855254.csv
```

The export is read-only and uses existing `zsxq_core` tables. Each row is one `group_id + signal_date + stock_name` signal with:

- `mention_count`: same-day recommendation-pool mentions from `zsxq_a_share_daily_mentions`.
- `topic_count`, `topic_ids`, `topic_titles`: topic-level evidence from `zsxq_a_share_topic_stock_extractions` plus topic metrics.
- `concepts`, `reasons`, `avg_confidence`, `max_confidence`: extraction evidence for audit and later factor review.
- `likes_count`, `comments_count`, `reading_count`: summed source-topic engagement metrics.

To run a first return smoke, use KnowActionSystem as the market-data source:

```powershell
uv run run-a-share-research-return-smoke --group-id 51111112855254 --start-date 2026-05-01 --end-date 2026-05-12 --hold-days 5 --output output\a_share_research\51111112855254_return_smoke.csv
```

The return smoke reads ZsxqCrawler signals, resolves stock codes through KnowActionSystem `stock_basic`, and reads KnowActionSystem `daily_quotes`. The first execution model is intentionally simple: signal day `T`, entry at `T+1` tradable open, exit at the `hold_days`-th tradable close after entry. Rows near the available quote tail may be flagged as `completed_forced_end_of_sample`; use earlier historical windows for formal performance conclusions.

## Access Rules

- `zsxq_reader` may `SELECT` from `zsxq_core`.
- `zsxq_reader` must not write, create tables, or manage schema objects.
- `zsxq_public` and legacy `zsxq_*` schemas are not part of the supported interface.
- Local `output/databases/{group_id}/downloads` and `images` directories contain resource files only; structured records are in PostgreSQL.

Before sharing a reader DSN, verify it:

```powershell
uv run verify-postgres-reader-access --dsn "<reader-dsn>"
```
