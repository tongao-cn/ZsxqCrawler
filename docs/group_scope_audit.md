# Group Scope Audit

Audit date: 2026-05-08

This audit covers code paths where a caller provides `group_id` and the code reads or writes shared PostgreSQL `zsxq_core` tables. The goal is to avoid cross-group reads, duplicate detection, downloads, statistics, or analysis state.

## Findings

| Area | Risk | Finding | Resolution |
| --- | --- | --- | --- |
| A-share topic scan | P0 | `read_topics_last_days(group_id, ...)` read all topics and compared them with one group's processed state. | Fixed before this audit: topics are filtered by `group_id`; talks are loaded only for those topic ids. |
| A-share source summary | P1 | `get_source_topics_summary(group_id)` counted all `topics`. | Fixed: summary counts and min/max times now filter by `group_id`. |
| File route list/status/stats | P0 | `/api/files/{group_id}`, `/status/{group_id}/{file_id}`, single-file download lookup, and file stats queried `files` without `group_id`. | Fixed: direct `files` queries include `group_id`; file list count uses the same scoped `WHERE`. |
| File route writes | P0 | Single-file download upsert could write a file row without `group_id`; local status reconciliation updated by `file_id` only. | Fixed: single-file upsert writes `group_id`; `ZSXQFileDatabase.update_file_download_status()` scopes by the database instance group. |
| File downloader collection/download | P0 | File time-range checks, latest-file dedupe, pending download selection, and size/time stats queried all files. | Fixed: downloader queries add `group_id` based on `self.group_id`. |
| Topic crawler duplicate checks | P0 | Topic duplicate checks used `topic_id` only in crawl modes. | Fixed: duplicate checks now use `topic_id` plus `group_id`. |
| Topic database timestamp/stats | P1 | `ZSXQDatabase` timestamp range and table stats were global even for group-bound instances. | Fixed: group-bound instances filter `topics` directly and child tables through topic ids. |
| Global table counts | P2 | `api_responses`, `collection_log`, and some admin/status reports remain global. | Kept intentionally because these tables do not carry reliable group ids. |

## Follow-up Rules

- If a route or service accepts `group_id`, direct tables with a `group_id` column must include it in SQL.
- If a child table lacks `group_id`, filter through `topics` or a scoped relation table.
- If a route accepts both `group_id` and `topic_id` or `file_id`, both identifiers must be validated in the query.
- Global aggregate paths must be named or documented as global.
