# Official Topic Crawl Flow Plan

## Goal

Use the official MCP topic flow as the default path while preserving the existing cookie-based crawler as an explicit switchable fallback.

## Scope

- Preserve all existing legacy crawl modes behind an explicit `legacy` source switch.
- Make official MCP the default source for topic crawls.
- Page official topics by `end_time`, then filter locally by the requested time range.
- De-duplicate topics by `topic_id` because official pagination can repeat the boundary row.
- Import topics through the existing PostgreSQL topic importer.
- Fetch comments through the official MCP path, not the legacy comment API.
- Read local topic lists/details/tags through `ZSXQDatabase` directly instead of constructing the legacy crawler.
- Fetch single-topic remote detail, refresh stats, and more-comments through official MCP.
- Fetch group list and group info through official MCP, with local fallback preserved.
- Read group stats and local file counts directly from PostgreSQL.
- Clear local topic/file/group data without instantiating the legacy crawler.
- Retry transient MCP HTTP transport failures, back off on MCP 429 responses, throttle tool calls, and redact MCP `api_key` from surfaced errors.

Out of scope for this slice:

- Changing database schema.
- Downloading files.

## Docs Checked

- `docs/project-architecture-roadmap.md`
- `docs/crawl_time_range_api_plan.md`
- `docs/zsxq-cli-poc-plan.md`

## Execution Steps

1. Add a production official topic client around the `zsxq-topic` MCP HTTP endpoint.
2. Normalize official topic payloads to the existing importer shape.
3. Add `topicSource` to the time-range crawl request.
4. Branch topic crawl tasks to official MCP unless `topicSource=legacy` or `ZSXQ_TOPIC_SOURCE=legacy`.
5. Keep `legacy` as an explicit fallback source.
6. Add focused tests for source resolution and official payload normalization.
7. Remove legacy crawler/runtime API dependencies from topic list/detail/tag/delete routes.
8. Move single-topic fetch, refresh, and comment fetch routes to MCP.
9. Move group list/info to MCP `get_self_info` / `get_user_groups`.
10. Remove crawler construction from group stats and local file-count helpers.
11. Remove crawler construction from local clear/delete operations that only need PostgreSQL or filesystem access.
12. Harden MCP JSON-RPC transport with retries for retryable network/5xx/429 failures, `Retry-After` support, tool-call throttling, task-log retry visibility, and secret redaction in error messages.

## Verification Plan

- Compile touched backend modules.
- Run focused crawl helper tests.
- Run official client helper tests.

## Progress

- POC confirmed official `get_group_topics` supports fast `end_time` pagination.
- POC confirmed 30-day read-only pull for group `51111112855254`: 145 pages, 4206 unique topics seen, no rate-limit failure.
- Official time-range source switch implemented.
- Frontend topic crawl actions now expose `旧 crawler` / `官方流程`.
- Official MCP is now the default crawl source in both backend source resolution and frontend controls.
- Official source branch implemented for latest, historical/incremental, all-history, and time-range topic crawl tasks.
- Live official time-range import test completed for `调研鹅纪要` (`15552822451452`) on `2026-05-21`: 3 pages, 61 new topics, 0 errors, 2 duplicate boundary rows skipped, 52 topic-file relations synced.
- Replaced the runtime official client from `zsxq-cli` subprocess calls with MCP HTTP JSON-RPC calls. Runtime official flow now requires `ZSXQ_TOPIC_MCP_URL`.
- Topic routes no longer instantiate the legacy crawler for local topic list/detail/tag/delete operations.
- Single-topic fetch, refresh, and more-comments routes now use official MCP `get_topic_info` / `get_topic_comments`.
- Group list/info routes now use official MCP `get_self_info` / `get_user_groups`; if MCP fails, existing local fallback still works.
- Group stats and local file counts now read PostgreSQL directly instead of constructing a legacy crawler.
- File database clear and local group delete no longer instantiate the legacy crawler just to close databases.
- MCP transport now retries retryable request failures up to 3 attempts, uses longer backoff for 429, respects `Retry-After`, throttles tool calls, writes retry waits into task logs, and redacts `api_key` in exception/log text.

## Runtime Configuration

Set the MCP URL in the backend process environment:

```powershell
ZSXQ_TOPIC_MCP_URL="https://mcp.zsxq.com/topic/mcp?api_key=..."
```

The URL is intentionally not stored in the repository.
For the local development workspace, the same key is stored in the untracked `.env` file and loaded by `OfficialTopicClient` without overriding real environment variables.

## Changed Files

- `backend/crawlers/official_topic_client.py`
- `backend/core/local_group_runtime.py`
- `backend/routes/file_routes.py`
- `backend/routes/group_routes.py`
- `backend/routes/topic_routes.py`
- `backend/schemas/crawl.py`
- `backend/services/crawl_service.py`
- `frontend/src/lib/api/groups.ts`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/components/CrawlLatestDialog.tsx`
- `frontend/src/components/CrawlPanel.tsx`
- `frontend/src/components/GroupActionPanel.tsx`
- `frontend/src/hooks/useCrawlActions.ts`
- `tests/test_crawl_routes_helpers.py`
- `tests/test_api_smoke.py`
- `tests/test_file_routes_helpers.py`
- `tests/test_group_routes_helpers.py`
- `tests/test_official_topic_client_helpers.py`
- `tests/test_topic_routes_helpers.py`

## Verification Results

- `uv run python -m py_compile backend\schemas\crawl.py backend\crawlers\official_topic_client.py backend\services\crawl_service.py`: passed.
- `uv run python -m unittest tests.test_crawl_routes_helpers tests.test_official_topic_client_helpers`: passed, 21 tests.
- `uv run python -m py_compile backend\routes\topic_routes.py backend\crawlers\official_topic_client.py`: passed.
- `uv run python -m unittest tests.test_topic_routes_helpers tests.test_official_topic_client_helpers tests.test_crawl_routes_helpers`: passed, 44 tests.
- `uv run python -m py_compile backend\routes\group_routes.py backend\crawlers\official_topic_client.py`: passed.
- `uv run python -m unittest tests.test_group_routes_helpers tests.test_official_topic_client_helpers`: passed, 20 tests.
- `uv run python -m py_compile backend\schemas\crawl.py backend\services\crawl_service.py backend\routes\group_routes.py backend\routes\topic_routes.py backend\crawlers\official_topic_client.py`: passed.
- `uv run python -m unittest tests.test_group_routes_helpers tests.test_topic_routes_helpers tests.test_official_topic_client_helpers tests.test_crawl_routes_helpers`: passed, 57 tests.
- `uv run python -m py_compile backend\routes\file_routes.py backend\core\local_group_runtime.py tests\test_api_smoke.py tests\test_file_routes_helpers.py`: passed.
- `uv run python -m unittest tests.test_file_routes_helpers tests.test_local_group_runtime tests.test_api_smoke tests.test_group_routes_helpers tests.test_topic_routes_helpers tests.test_official_topic_client_helpers tests.test_crawl_routes_helpers`: passed, 76 tests.
- `uv run python -m py_compile backend\crawlers\official_topic_client.py backend\services\crawl_service.py backend\routes\group_routes.py backend\routes\topic_routes.py`: passed.
- `uv run python -m unittest tests.test_group_routes_helpers tests.test_topic_routes_helpers tests.test_official_topic_client_helpers tests.test_crawl_routes_helpers tests.test_file_routes_helpers tests.test_local_group_runtime tests.test_api_smoke`: passed, 78 tests.
- `uv run python -m py_compile backend\crawlers\official_topic_client.py backend\services\crawl_service.py backend\routes\group_routes.py backend\routes\topic_routes.py`: passed after 429 backoff/throttle update.
- `uv run python -m unittest tests.test_group_routes_helpers tests.test_topic_routes_helpers tests.test_official_topic_client_helpers tests.test_crawl_routes_helpers tests.test_file_routes_helpers tests.test_local_group_runtime tests.test_api_smoke`: passed, 81 tests.
- `npm run build` in `frontend`: passed.
- `uv run python scripts\probe_zsxq_mcp_range_pull.py --group-id 15552822451452 --begin-time "2026-05-21T00:00:00.000+0800" --end-time "2026-05-21T23:59:59.999+0800" --limit 30 --max-pages 500`: passed, 61 unique matched topics.
- `OfficialTopicClient()` with no pre-set environment variable loaded `ZSXQ_TOPIC_MCP_URL` from local `.env` and fetched one live topic from group `15552822451452`: passed.
