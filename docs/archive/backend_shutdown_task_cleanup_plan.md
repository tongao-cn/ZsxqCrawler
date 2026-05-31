# Backend Shutdown Task Cleanup

## Goal

Make Ctrl+C shutdown more predictable by asking in-memory tasks, crawler instances, downloader instances, and task log streams to stop when FastAPI lifespan exits.

## Scope

- Add a small task-runtime shutdown helper.
- Call the helper from `backend/main.py` lifespan shutdown.
- Run long task work in runtime-owned daemon threads instead of FastAPI `BackgroundTasks`.
- Preserve existing task creation, stop API, and persisted task semantics.
- Do not force-kill Python threads or change long-running worker implementation.

## Docs Checked

- `README.md`
- `docs/project-architecture-roadmap.md`
- `docs/task-list-residual-task-handling-plan.md`

## Execution Steps

1. Add a `request_runtime_shutdown()` helper in `backend/services/task_runtime.py`.
2. Mark pending/running in-memory tasks as cancelled, set stop flags, and signal registered crawler/downloader instances.
3. Clear in-memory SSE connection bookkeeping.
4. Call the helper from FastAPI lifespan shutdown.
5. Move route task enqueueing away from FastAPI `BackgroundTasks`.
6. Verify with targeted task runtime and route helper tests.

## Verification Plan

```powershell
python -m pytest tests/test_task_runtime_helpers.py
python -m pytest tests/test_ingestion_helpers.py tests/test_columns_routes_helpers.py tests/test_file_routes_helpers.py tests/test_daily_analysis_routes_helpers.py tests/test_daily_stock_concept_routes_helpers.py tests/test_a_share_routes_helpers.py
```

## Progress

- 2026-05-10: Plan created.
- 2026-05-10: Added shutdown cleanup helper and lifespan integration.
- 2026-05-10: Verified targeted task runtime tests and backend module compilation.
- 2026-05-10: Confirmed the remaining hang came from FastAPI `BackgroundTasks` graceful-wait behavior.
- 2026-05-10: Added runtime daemon-thread task enqueueing for long task routes.
- 2026-05-10: Verified targeted route helper tests and local start/stop smoke checks.

## Changed Files

- `backend/main.py`
- `backend/services/task_runtime.py`
- `backend/routes/a_share_routes.py`
- `backend/routes/columns_routes.py`
- `backend/routes/daily_analysis_routes.py`
- `backend/routes/daily_stock_concept_routes.py`
- `backend/routes/file_routes.py`
- `backend/routes/ingestion_helpers.py`
- `tests/test_task_runtime_helpers.py`
- `tests/test_columns_routes_helpers.py`
- `tests/test_daily_analysis_routes_helpers.py`
- `tests/test_file_routes_helpers.py`
- `tests/test_ingestion_helpers.py`
- `docs/backend_shutdown_task_cleanup_plan.md`

## Verification Results

```powershell
python -m pytest tests/test_task_runtime_helpers.py
# 6 passed

python -m py_compile backend\main.py backend\services\task_runtime.py
# passed

python -m pytest tests/test_task_runtime_helpers.py tests/test_ingestion_helpers.py tests/test_columns_routes_helpers.py tests/test_file_routes_helpers.py tests/test_daily_analysis_routes_helpers.py tests/test_daily_stock_concept_routes_helpers.py tests/test_a_share_routes_helpers.py
# 34 passed, 27 skipped

python -m py_compile backend\services\task_runtime.py backend\routes\ingestion_helpers.py backend\routes\columns_routes.py backend\routes\file_routes.py backend\routes\daily_analysis_routes.py backend\routes\daily_stock_concept_routes.py backend\routes\a_share_routes.py
# passed

# Local smoke:
# start backend on port 8519, stop process, exited within 5s
# start backend on port 8520, create /api/files/collect/0 task, stop process, exited within 5s
# start backend on port 8521, /api/files/collect/0 returned 409 due existing ingestion task, stop process, exited within 5s
```
