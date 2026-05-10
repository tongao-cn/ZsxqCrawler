# High Priority Backend And Page Optimization Plan

## Status

Complete.

## Goal

Close the high-priority review items without changing public API paths, database schema, UI layout, or user-visible workflow semantics.

## Scope

- Thin backend route modules where helpers can move safely into services.
- Unify task creation paths for stock topic analysis.
- Remove route-to-route imports between daily analysis and crawl routes.
- Split the frontend API client behind the existing `apiClient` compatibility export.
- Extract stock topic task polling from the component into a hook.

## Docs Checked

- `AGENTS.md`
- `README.md`
- `docs/project-architecture-roadmap.md`

## Execution Steps

1. Add this tracking doc.
2. Move shared crawl request schemas out of routes.
3. Switch stock topic analysis task creation to runtime tasks.
4. Move file workflow helpers and task functions into a service while preserving route exports.
5. Move low-risk topic/column helpers into services.
6. Split frontend API client by domain and keep the public facade compatible.
7. Verify stock topic task polling is centralized through the existing task hook.
8. Run targeted backend tests, backend smoke tests, frontend build, and frontend lint.

## Verification Results

- `uv run python -m pytest ...` was attempted first, but this environment does not have `pytest` installed.
- `uv run python -m unittest tests.test_stock_topic_analysis_routes_helpers tests.test_daily_analysis_routes_helpers tests.test_crawl_routes_helpers tests.test_file_routes_helpers tests.test_ingestion_helpers tests.test_task_runtime_helpers` passed: 47 tests.
- `uv run python -m unittest tests.test_topic_routes_helpers tests.test_columns_routes_helpers` passed: 50 tests.
- `uv run python -m unittest tests.test_api_smoke tests.test_app_factory` passed: 5 tests.
- `$env:PYTHONIOENCODING='utf-8'; uv run python -m unittest discover -s tests` passed: 298 tests, 15 skipped.
- `uv run python -m py_compile backend\schemas\crawl.py backend\schemas\files.py backend\services\file_workflow_service.py backend\services\topic_workflow_service.py backend\services\columns_summary_service.py backend\routes\crawl_routes.py backend\routes\daily_analysis_routes.py backend\routes\stock_topic_analysis_routes.py backend\routes\file_routes.py backend\routes\topic_routes.py backend\routes\columns_routes.py` passed.
- `cd frontend; npm run build` passed.
- `cd frontend; npm run lint` passed.

## Notes

- `daily_analysis_routes.py` now imports crawl request schema/service code directly instead of depending on `crawl_routes.py`.
- Stock topic analysis task creation now uses the runtime task queue and keeps the same task response shape.
- File workflow helpers and task functions live in `backend/services/file_workflow_service.py`; route endpoints still own request/HTTP exception mapping.
- Frontend API calls are split under `frontend/src/lib/api/`, while `frontend/src/lib/api.ts` remains the compatibility facade for `apiClient`, error helpers, and exported types.
