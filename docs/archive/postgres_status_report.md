# PostgreSQL Status Report

Generated at: 2026-05-07T15:35:06.355957+00:00

## PostgreSQL Core Schema

| Schema | Tables | Rows |
| --- | ---: | ---: |
| `zsxq_core` | 36 | 126566 |

## Group ID Quality

| Metric | Rows |
| --- | ---: |
| `comments_null_group_id` | 0 |
| `files_null_group_id` | 0 |
| `file_ai_analyses_null_group_id` | 0 |
| `files_ambiguous_group_id` | 0 |

## Notes

- Applications read and write `zsxq_core` directly.
- Other projects should use a read-only role with SELECT on `zsxq_core`.
- Re-run this report after PostgreSQL data refresh or cleanup.
