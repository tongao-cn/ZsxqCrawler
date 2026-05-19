# Stock Topic Analysis Tab Plan

## Goal

Add a group-page tab where the user can enter one or more stock names, review saved report status, recommendation counts, and trigger AI summaries based on recommendation-pool excerpts.

Add a sibling A-share Q&A tab where the user can enter a free-form question, let AI extract topic-search keywords, search matched topics, and trigger an AI summary based only on matched topic content.

## Scope

- Group workbench at `/groups/[groupId]`.
- Read-only topic search against existing PostgreSQL data.
- Read-only use of existing A-share topic extractions and daily recommendation mentions.
- One task-based AI analysis action over the searched topic payload.
- Batch stock-topic analysis with one row per stock and one saved latest result per group and stock.
- Image-assisted stock-name extraction that fills the multi-stock input box before search or analysis.
- Persist the latest analysis result per group and stock.
- Free-form A-share Q&A over existing group topics without adding a new persistence table.
- A-share Q&A keyword extraction should use AI first, not hard-coded Chinese question suffix rules.
- Incremental stock analysis: one saved result per group and stock, with analyzed topic IDs recorded so later runs only send newly discovered topics to AI and merge the new evidence into the saved result.

## Constraints

- Do not change the A-share recommendation pool output.
- Do not change the existing daily stock concept workflow.
- Do not crawl new data from this tab.
- Keep the workflow group-scoped.

## Docs Checked

- `AGENTS.md`
- `docs/project-architecture-roadmap.md`
- `docs/group_sidebar_context_actions_plan.md`

## Execution Steps

1. Add backend service helpers for stock-name topic search and AI summary.
2. Add bounded FastAPI routes under a separate stock-topic-analysis prefix.
3. Add frontend API types and methods.
4. Add a focused group-page panel and a separate tab.
5. Run targeted backend tests and frontend build.
6. Convert one-click analysis to a background task and save the latest analysis result.
7. Refresh the panel from the saved result when the task completes.
8. Upgrade the tab to support multi-stock input, batch preview, batch background analysis, and a per-stock result dialog.
9. Add an image extraction action that sends one uploaded image to AI and merges extracted stock names back into the input.
10. Add an A-share Q&A tab that uses AI to extract keywords from the question, previews matched topics, and runs a background AI summary task.
11. Upgrade stock analysis persistence so latest-result reads include the analyzed topic list, and analysis tasks initialize missing rows or incrementally update existing rows only when new topics are found.

## Progress

- Plan created.
- Backend stock-topic search and AI summary service added.
- FastAPI routes added under `/api/analysis/stock-topics`.
- Frontend API types and methods added.
- Group page now includes a separate `个股话题` tab with search, topic table, concept badges, recommendation count, and one-click AI analysis.
- One-click analysis now creates a `stock_topic_analysis` task.
- Latest analysis results are persisted in `stock_topic_analyses` and loaded after task completion.
- Multi-stock input now supports whitespace, comma, Chinese comma, semicolon, and dunhao separators, dedupes names, and caps each batch at 20 stocks.
- Batch analysis now creates a `stock_topic_analysis_batch` task and saves each stock into the existing `stock_topic_analyses` table.
- The results area now renders a table with status per stock and a dialog for the saved Markdown summary.
- The tab now accepts one JPG/PNG/WebP image up to 4MB and uses the configured AI provider to extract stock names into the input box.
- A sibling `A股问答` tab now accepts a free-form question, uses AI to extract search keywords, searches group topics, and creates a `stock_question_analysis` task for AI summary.
- The stock-topic AI summary prompt now uses a company-summary structure covering one-line intro, concepts, business mix, customers, event drivers, forward market cap/revenue/profit by time and sell-side/source, risks, and source topic indexes.
- Incremental stock analysis now reuses `stock_topic_analyses.topic_ids_json` as the analyzed-topic ledger, keeps one row per group and stock, returns the saved topic list from latest-result reads, skips AI when there are no new topics, and sends only new topic payloads when updating an existing summary.
- Stock analysis now searches recent one-year candidate topics without the previous 80 matched-topic cap, then processes newly discovered topics in AI chunks of up to 10 topics per call.
- Stock analysis now extracts or trims current-stock content from candidate topics before AI analysis, and records per-topic processed state in `stock_topic_processed_states` with statuses such as `analyzed`, `skipped`, and `failed`.
- The frontend now distinguishes saved-query, initialization, incremental-update, and up-to-date states with new-topic counts.
- Recommendation-pool topic extraction now stores a per-stock `excerpt`; individual stock analysis uses this stored evidence excerpt for search previews and AI report payloads, and reports an error when a matched topic has no excerpt.
- Stock analysis now treats recommendation-pool excerpts as the primary search and analysis source. The frontend focuses on report/status/counts instead of exposing topic details, while the backend keeps topic IDs for counting and incremental processed-state tracking.

## Changed Files

- `backend/main.py`
- `backend/routes/stock_topic_analysis_routes.py`
- `backend/services/stock_topic_analysis_service.py`
- `backend/storage/postgres_core_schema.py`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/components/StockTopicAnalysisPanel.tsx`
- `frontend/src/components/StockQuestionPanel.tsx`
- `frontend/src/lib/api.ts`
- `tests/test_stock_topic_analysis_routes_helpers.py`
- `tests/test_stock_topic_analysis_service_helpers.py`
- `tests/test_postgres_core_schema.py`
- `docs/stock-topic-analysis-tab-plan.md`

## Verification Results

- `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers`: passed.
- `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py backend\main.py`: passed.
- `cd frontend; npx tsc --noEmit --pretty false`: passed.
- `cd frontend; npm run build`: compiled successfully and passed type checking, then failed during Next trace/page-data collection with `Cannot find module for page: /groups/[groupId]/columns`. The route file exists at `frontend/src/app/groups/[groupId]/columns/page.tsx`; this is recorded as a residual Next build collection issue outside the new tab's type surface.
- `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers tests.test_postgres_core_schema`: passed.
- `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py backend\storage\postgres_core_schema.py backend\main.py`: passed.
- `cd frontend; npx tsc --noEmit --pretty false`: passed after task/persistence conversion.
- `uv run manage-postgres-core-schema --apply`: timed out while waiting on PostgreSQL locks.
- Targeted DDL for `stock_topic_analyses`: also timed out waiting on locks. `pg_stat_activity` showed existing idle-in-transaction sessions on account reads and blocked DDL sessions; the blocked DDL sessions were cancelled with `pg_cancel_backend`. Runtime table creation still needs to be retried after the blocking sessions are released.
- A-share Q&A pass: `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers`: passed.
- A-share Q&A pass: `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py backend\main.py`: passed.
- A-share Q&A pass: `cd frontend; npx tsc --noEmit --pretty false`: passed.
- A-share Q&A pass: `cd frontend; npm run build`: passed.
- A-share Q&A AI-keyword pass: `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers`: passed.
- A-share Q&A AI-keyword pass: `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py`: passed.
- A-share Q&A AI-keyword pass: `cd frontend; npx tsc --noEmit --pretty false`: passed.
- A-share Q&A AI-keyword pass: `cd frontend; npm run build`: passed.
- Incremental stock-analysis pass: `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py backend\storage\postgres_core_schema.py`: passed.
- Incremental stock-analysis pass: `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers tests.test_postgres_core_schema`: passed.
- Incremental stock-analysis pass: `cd frontend; npx tsc --noEmit --pretty false`: passed.
- Incremental stock-analysis chunking pass: `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py backend\storage\postgres_core_schema.py`: passed.
- Incremental stock-analysis chunking pass: `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers tests.test_postgres_core_schema`: passed.
- Incremental stock-analysis chunking pass: `cd frontend; npx tsc --noEmit --pretty false`: passed.
- Incremental stock-analysis screening pass: `uv run python -m py_compile backend\services\stock_topic_analysis_service.py backend\routes\stock_topic_analysis_routes.py backend\storage\postgres_core_schema.py`: passed.
- Incremental stock-analysis screening pass: `uv run python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_stock_topic_analysis_routes_helpers tests.test_postgres_core_schema`: passed.
- Incremental stock-analysis screening pass: `cd frontend; npx tsc --noEmit --pretty false`: passed.
- Recommendation-pool excerpt integration pass: `python -m unittest tests.test_stock_topic_analysis_service_helpers tests.test_a_share_analysis_service_helpers tests.test_a_share_analysis_db_storage_helpers tests.test_postgres_core_schema`: passed.
- Recommendation-pool excerpt integration pass: `python -m py_compile backend/services/stock_topic_analysis_service.py backend/services/a_share_analysis_service.py backend/services/a_share_analysis_db_storage.py backend/storage/postgres_core_schema.py`: passed.
- Excerpt-first stock analysis pass: `python -m unittest tests.test_stock_topic_analysis_service_helpers`: passed.
- Excerpt-first stock analysis pass: `python -m py_compile backend\services\stock_topic_analysis_service.py`: passed.
- Excerpt-first stock analysis pass: `cd frontend; npx tsc --noEmit --pretty false`: passed.
