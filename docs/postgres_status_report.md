# PostgreSQL Status Report

Generated at: 2026-05-07T13:30:51.675741+00:00

## PostgreSQL Core Schema

| Schema | Tables | Rows |
| --- | ---: | ---: |
| `zsxq_core` | 37 | 258121 |

## Public Views

| View | Rows |
| --- | ---: |
| `zsxq_public.groups` | 2 |
| `zsxq_public.topics` | 12962 |
| `zsxq_public.comments` | 121 |
| `zsxq_public.files` | 20877 |
| `zsxq_public.columns` | 0 |
| `zsxq_public.column_topics` | 0 |
| `zsxq_public.daily_ai_reports` | 5 |
| `zsxq_public.file_ai_analyses` | 7 |

## Group ID Quality

| Metric | Rows |
| --- | ---: |
| `comments_null_group_id` | 0 |
| `files_null_group_id` | 0 |
| `file_ai_analyses_null_group_id` | 0 |
| `files_ambiguous_group_id` | 0 |

## Notes

- Other projects should read from `zsxq_public` with the reader DSN.
- Legacy archived `zsxq_*` schema count: 594.
- Re-run this report after any PostgreSQL public view or data refresh.
