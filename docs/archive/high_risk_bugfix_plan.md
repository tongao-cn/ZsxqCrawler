# High Risk Bugfix Plan

## Goal

Fix the confirmed and high-risk crawler/task bugs without broad refactors:

- Stop bounded topic crawls after an empty page.
- Avoid repeating the same file/topic page when pagination cannot advance.
- Make task cancellation stop the task-owned crawler/downloader instance.
- Prevent stale daily-analysis frontend requests from overwriting newer state.

## Docs Checked

- `docs/crawl_time_range_api_plan.md`
- Prior repo scan notes in Codex memory for ZsxqCrawler hotspots and verification expectations.

## Scope

- Backend crawler pagination and task runtime cancellation only.
- Daily topic analysis frontend request cancellation only.
- No API shape changes beyond internal optional `AbortSignal` support.
- No large component split, route extraction, or unrelated cleanup.

## Progress

- Time-range topic crawl now exits the outer loop after `topics=[]`.
- File collection now stops when a fetched page cannot be imported, instead of retrying the same cursor forever.
- Topic pagination now stops when a successful page lacks a usable last `create_time`.
- Task runtime can register and stop task-owned crawler instances by task id.
- Daily analysis panel requests now use abort protection for group/date-driven loads.

## Changed Files

- `backend/services/task_runtime.py`
- `backend/routes/crawl_routes.py`
- `backend/crawlers/zsxq_interactive_crawler.py`
- `backend/crawlers/zsxq_file_downloader.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/DailyTopicAnalysisPanel.tsx`
- `tests/test_crawl_routes_helpers.py`
- `tests/test_task_runtime_helpers.py`
- `tests/test_zsxq_file_downloader_helpers.py`
- `tests/test_zsxq_interactive_crawler_helpers.py`

## Verification Plan

- `python -m pytest tests/test_crawl_routes_helpers.py tests/test_zsxq_file_downloader_helpers.py tests/test_zsxq_interactive_crawler_helpers.py tests/test_task_runtime_helpers.py`
- `python -m py_compile backend/crawlers/zsxq_interactive_crawler.py backend/crawlers/zsxq_file_downloader.py backend/routes/crawl_routes.py backend/services/task_runtime.py`
- `npm run build` in `frontend`

## Verification Results

- `python -m pytest tests/test_crawl_routes_helpers.py tests/test_zsxq_file_downloader_helpers.py tests/test_zsxq_interactive_crawler_helpers.py tests/test_task_runtime_helpers.py`: passed, 22 tests.
- `python -m py_compile backend/crawlers/zsxq_interactive_crawler.py backend/crawlers/zsxq_file_downloader.py backend/routes/crawl_routes.py backend/services/task_runtime.py`: passed.
- `npx tsc --noEmit --pretty false` in `frontend`: passed.
- `npx eslint src/components/DailyTopicAnalysisPanel.tsx src/lib/api.ts` in `frontend`: passed.
- `npm run build` in `frontend`: failed on pre-existing unrelated lint errors in `src/components/AShareAnalysisPanel.tsx` (`advancedOpen` and `setAdvancedOpen` unused); production compilation completed before lint/type validation stopped.
