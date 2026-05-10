# Group File Workbench Redesign Plan

## Goal

Make the group file tab read as one clear workbench: search/filter files, download or retry missing files, analyze downloaded files, and view existing analysis from the central table. Keep the right sidebar as a launcher for long-running download tasks and settings.

## Scope

- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/components/GroupActionPanel.tsx`
- No backend API or storage changes.
- No changes to topic crawling, A-share analysis, or daily summary behavior.

## Constraints

- Preserve the current four-tab group page shape.
- Keep the file page as a management surface for synced file records.
- Keep the change narrow and compatible with existing `/api/files` status filtering.

## Docs Checked

- `AGENTS.md`
- `docs/group_sidebar_context_actions_plan.md`
- User-approved v2 file-workbench concept from this thread.

## Execution Steps

1. Add central file-workbench affordances: clearer title, current-filter summary, separate get/analyze status controls, and batch actions.
2. Keep row-level primary action deterministic: download, retry, AI analysis, or view analysis.
3. Reframe the right file sidebar as a long-task launcher and move database deletion into a weaker danger section.
4. Run the smallest meaningful frontend verification.

## Progress

- Added a central file workbench header, current-filter summary, separate get/analyze status controls, and current-page batch download/analyze actions.
- Kept row-level primary actions deterministic: download/retry for unavailable files, AI analysis for downloaded files, and view analysis for analyzed files.
- Reframed the file-mode right sidebar as a long-task launcher and folded database deletion into a weaker danger section.

## Changed Files

- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/components/GroupActionPanel.tsx`
- `docs/group_file_workbench_redesign_plan.md`

## Verification Results

- `npm run build` in `frontend`: passed.
- `Invoke-WebRequest http://localhost:3060/groups/51111112855254`: returned `200`.
- Browser plugin validation attempted, but the in-app browser automation timed out on this data-heavy group page before a snapshot was available.
- Headless Chrome/CDP validation clicked the `文件` tab and confirmed rendered text for `文件工作台`, `任务启动器`, and `只看需处理`; the temporary screenshot was inspected and then removed.
