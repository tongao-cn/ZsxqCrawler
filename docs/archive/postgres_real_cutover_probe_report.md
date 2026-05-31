# PostgreSQL Real Cutover Probe Report

Generated at: 2026-05-07T15:34:36.579556+00:00

- Mode: `apply`
- Group ID: `51111112855254`
- Requested latest topic count: 5
- Crawl result: `{'api_succeeded': True, 'new_topics': 5, 'updated_topics': 0, 'errors': 0}`
- Apply mode fetches only the latest topic-list API payload and intentionally skips extra comment pagination.

## Counts

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `legacy_schema_count` | 0 | 0 | 0 |
| `core_topics` | 13121 | 13126 | 5 |
| `core_files` | 20877 | 20902 | 25 |
| `core_comments` | 121 | 121 | 0 |
| `core_tasks` | 64 | 64 | 0 |

## Verification

- Legacy schema count did not increase.
