# Crawl Time Range API Plan

## Goal

Use a constrained frontend workflow for bounded topic crawls: recent-N-days remains available, month selection is available, and arbitrary custom start/end date input is removed. Month crawls are backed by the ZSXQ topics API `begin_time` and `end_time` parameters.

## Scope

- Topic crawl UI: remove arbitrary custom start/end date controls from crawl entry points.
- Keep recent-N-days topic crawling.
- Add month selection for bounded topic crawling.
- Backend topic time-range crawl parameter handling.
- Keep local `create_time` filtering as a safety check.
- Do not change unrelated crawl modes or frontend layout.

## Docs Checked

- `docs/` has no active crawl-specific plan.
- Existing group-scope docs are not directly about request pagination semantics.

## Execution Steps

1. Frontend keeps recent-N-days bounded crawling.
2. Frontend accepts month selection instead of arbitrary custom start/end dates.
3. Convert the selected month to start/end dates before calling the existing range endpoint.
4. Send `begin_time` with the selected start time and initialize `end_time` from the selected end time.
5. Treat date-only `endTime` as the end of that calendar day.
6. Add concise per-page logs showing fetched topics and in-range topics.
7. Add targeted helper tests and run them.

## Verification Plan

- Run `python -m pytest tests/test_crawl_routes_helpers.py`.

## Progress

- Backend API parameter support started.
- Frontend keeps recent-N-days and month-only UI completed.
- Backend date-boundary tests completed.

## Changed Files

- `backend/crawlers/zsxq_interactive_crawler.py`
- `backend/routes/crawl_routes.py`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/components/CrawlLatestDialog.tsx`
- `frontend/src/components/CrawlPanel.tsx`
- `frontend/src/components/GroupActionPanel.tsx`
- `frontend/src/hooks/useCrawlActions.ts`
- `tests/test_crawl_routes_helpers.py`

## Verification Results

- `python -m pytest tests/test_crawl_routes_helpers.py`: passed.
- `npm run build` in `frontend`: passed.
