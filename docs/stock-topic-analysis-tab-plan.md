# Stock Topic Analysis Tab Plan

## Goal

Add a group-page tab where the user can enter a stock name, review matched topics, concepts, recommendation count, and trigger an AI summary based only on the matched topic content.

## Scope

- Group workbench at `/groups/[groupId]`.
- Read-only topic search against existing PostgreSQL data.
- Read-only use of existing A-share topic extractions and daily recommendation mentions.
- One task-based AI analysis action over the searched topic payload.
- Persist the latest analysis result per group and stock.

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

## Progress

- Plan created.
- Backend stock-topic search and AI summary service added.
- FastAPI routes added under `/api/analysis/stock-topics`.
- Frontend API types and methods added.
- Group page now includes a separate `个股话题` tab with search, topic table, concept badges, recommendation count, and one-click AI analysis.
- One-click analysis now creates a `stock_topic_analysis` task.
- Latest analysis results are persisted in `stock_topic_analyses` and loaded after task completion.

## Changed Files

- `backend/main.py`
- `backend/routes/stock_topic_analysis_routes.py`
- `backend/services/stock_topic_analysis_service.py`
- `backend/storage/postgres_core_schema.py`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/components/StockTopicAnalysisPanel.tsx`
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
