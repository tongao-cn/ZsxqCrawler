# PostgreSQL Status Report

Generated at: 2026-05-07T10:35:45.758241+00:00

## PostgreSQL Core Schema

| Schema | Tables | Rows |
| --- | ---: | ---: |
| `zsxq_core` | 37 | 258046 |

## Public Views

| View | Rows |
| --- | ---: |
| `zsxq_public.groups` | 2 |
| `zsxq_public.topics` | 12960 |
| `zsxq_public.comments` | 121 |
| `zsxq_public.files` | 20875 |
| `zsxq_public.columns` | 0 |
| `zsxq_public.column_topics` | 0 |
| `zsxq_public.daily_ai_reports` | 5 |
| `zsxq_public.file_ai_analyses` | 7 |

## Notes

- Other projects should read from `zsxq_public` with the reader DSN.
- Legacy archived `zsxq_*` schema count: 594.
- `files.group_id` and `file_ai_analyses.group_id` may remain `NULL` when no reliable group relation exists.
- Re-run this report after any PostgreSQL public view or data refresh.
