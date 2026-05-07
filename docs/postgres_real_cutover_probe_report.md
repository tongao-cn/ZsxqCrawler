# PostgreSQL Real Cutover Probe Report

Generated at: 2026-05-07T11:53:22.031795+00:00

- Mode: `apply`
- Group ID: `15552822451452`
- Requested latest topic count: 1
- Crawl result: `{'api_succeeded': True, 'new_topics': 1, 'updated_topics': 0, 'errors': 0}`
- Apply mode fetches only the latest topic-list API payload and intentionally skips extra comment pagination.

## Counts

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `legacy_schema_count` | 594 | 594 | 0 |
| `core_topics` | 12960 | 12961 | 1 |
| `core_files` | 20875 | 20875 | 0 |
| `core_comments` | 121 | 121 | 0 |
| `core_tasks` | 59 | 59 | 0 |
| `public_topics` | 12960 | 12961 | 1 |
| `public_files` | 20875 | 20875 | 0 |
| `public_comments` | 121 | 121 | 0 |

## Verification

- Legacy schema count did not increase.
