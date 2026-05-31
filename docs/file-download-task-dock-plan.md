# File Download Task Dock Plan

## Goal

Make file-workbench download actions participate in the group page task dock instead of only showing row-level file status.

## Scope

- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `docs/file-download-task-dock-plan.md`

## Constraints

- Do not change backend task creation; file download routes already create `download_single_file` and `download_files` tasks.
- Preserve row-level download status in the file workbench.
- Keep the change scoped to task visibility and conflict handling.

## Docs Checked

- `AGENTS.md`
- `docs/project-architecture-roadmap.md`
- `docs/group_file_workbench_redesign_plan.md`

## Execution Steps

1. Add optional task callbacks to the group file workbench.
2. Notify the page-level task bridge when single-file and current-page download tasks are created.
3. Route ingestion-task conflicts to the page task list.
4. Run focused frontend verification.

## Progress

- Added optional task callbacks to the group file workbench.
- Single-file downloads now notify the group page task bridge when a `task_id` is returned.
- Current-page batch download task creation now notifies the task bridge for each created `task_id`.
- Download task conflicts now open the task list instead of only showing a row-level failure prompt.

## Changed Files

- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `docs/file-download-task-dock-plan.md`

## Verification Results

- `npm run build` in `frontend`: passed.
