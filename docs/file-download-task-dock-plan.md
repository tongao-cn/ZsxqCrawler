# File Workflow Task Plan

## Goal

Make file download, file sync, and file AI analysis behave like durable group tasks, while tightening download correctness and keeping the file workbench deterministic.

## Scope

- `backend/crawlers/zsxq_file_downloader.py`
- `backend/routes/file_routes.py`
- `backend/routes/task_routes.py`
- `backend/schemas/files.py`
- `backend/services/file_workflow_service.py`
- `backend/services/task_runtime.py`
- `frontend/src/components/DataPanel.tsx`
- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/components/TaskListCompact.tsx`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/lib/api/files.ts`
- `frontend/src/lib/api/tasks.ts`
- `tests/test_file_routes_helpers.py`
- `tests/test_zsxq_file_downloader_helpers.py`
- `docs/file-download-task-dock-plan.md`

## Constraints

- Leave unrelated dirty worktree changes untouched.
- Keep downloads group-scoped and serialized behind the existing ingestion lock.
- Keep file AI analysis separate from ingestion locks, but include group metadata so it appears in the group task dock.
- Preserve the existing synchronous file analysis endpoint for compatibility.

## Docs Checked

- `AGENTS.md`
- `docs/project-architecture-roadmap.md`
- `docs/file-download-runtime-fix-plan.md`

## Execution Steps

1. Make downloader writes strict: download into `.part`, validate size, then atomically replace the final file.
2. Add selected-file download and file-analysis task APIs.
3. Move topic-file sync into the background task runtime.
4. Expand file search beyond file name and remove GET-side status writes.
5. Wire the file workbench to selected download and AI analysis tasks.
6. Run focused backend tests and frontend build.

## Progress

- Completed.
- File downloads now fail instead of marking truncated files completed.
- API code `1030` now skips the current file without stopping the whole batch.
- Current-page and selected-file downloads now create one backend `download_selected_files` task.
- Topic-file sync now creates a background `sync_files_from_topics` task.
- Single-file and batch file AI analysis can now run as `analyze_file` / `analyze_files` tasks.
- File list search now includes related topic/article/talk text.
- File list GET no longer writes download status as a side effect.
- Task listing supports server-side group/type filters.

## Changed Files

- `backend/crawlers/zsxq_file_downloader.py`
- `backend/routes/file_routes.py`
- `backend/routes/task_routes.py`
- `backend/schemas/files.py`
- `backend/services/file_workflow_service.py`
- `backend/services/task_runtime.py`
- `frontend/src/components/DataPanel.tsx`
- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/components/TaskListCompact.tsx`
- `frontend/src/lib/api/files.ts`
- `frontend/src/lib/api/tasks.ts`
- `tests/test_file_routes_helpers.py`
- `tests/test_zsxq_file_downloader_helpers.py`
- `docs/file-download-task-dock-plan.md`

## Verification Results

- `$env:PYTHONIOENCODING='utf-8'; uv run python -m unittest tests.test_file_routes_helpers tests.test_zsxq_file_downloader_helpers tests.test_task_routes_helpers tests.test_task_runtime_helpers`: passed.
- `npm run build` in `frontend`: passed.
