# Backend Shutdown Task Cleanup

## Goal

Make Ctrl+C shutdown more predictable by asking in-memory tasks, crawler instances, downloader instances, and task log streams to stop when FastAPI lifespan exits.

## Scope

- Add a small task-runtime shutdown helper.
- Call the helper from `backend/main.py` lifespan shutdown.
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
5. Verify with targeted task runtime tests.

## Verification Plan

```powershell
python -m pytest tests/test_task_runtime_helpers.py
```

## Progress

- 2026-05-10: Plan created.
- 2026-05-10: Added shutdown cleanup helper and lifespan integration.
- 2026-05-10: Verified targeted task runtime tests and backend module compilation.

## Changed Files

- `backend/main.py`
- `backend/services/task_runtime.py`
- `tests/test_task_runtime_helpers.py`
- `docs/backend_shutdown_task_cleanup_plan.md`

## Verification Results

```powershell
python -m pytest tests/test_task_runtime_helpers.py
# 6 passed

python -m py_compile backend\main.py backend\services\task_runtime.py
# passed
```
