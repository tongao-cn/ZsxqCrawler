# Web High Priority Optimization Plan

## Goal

Close the current high-priority web optimization slice: reduce group-workbench first-load pressure, keep daily report and stock-concept loading separate, load topic details on demand, and consolidate task-status watching.

## Scope

- `/groups/[groupId]` data loading and topic detail behavior.
- Daily report / stock concept panel request boundaries.
- Shared frontend task-status tracking for long-running task follow-up.
- No backend task API changes and no visual redesign.

## Docs Checked

- `AGENTS.md`
- `docs/project-architecture-roadmap.md`
- `docs/group_sidebar_context_actions_plan.md`
- `docs/group_file_workbench_redesign_plan.md`

## Execution Steps

1. Record frontend build baseline.
2. Gate daily-report and stock-concept requests by panel mode.
3. Defer non-critical group loaders.
4. Replace page-wide topic detail prefetch with on-demand detail cache.
5. Reuse a shared task-status hook for single-file download, stock-topic analysis, and A-share refresh follow-up.
6. Run targeted backend task smoke plus frontend build and runtime checks.

## Progress

- Baseline frontend build passed before changes.
- Baseline route sizes: `/groups/[groupId]` First Load JS `205 kB`; `/groups/[groupId]/columns` First Load JS `173 kB`.
- Daily report mode now only loads daily-report data; stock-concepts mode owns stock concepts, concept trend, and recommendation-hit requests.
- Group workbench non-critical loaders now run after the critical group detail/stat bootstrap instead of in the blocking initial loader set.
- Topic details now use an on-demand cache loaded from expand/comment actions instead of prefetching the whole current page.
- Single-file download, group file-table download tasks, stock-topic analysis, and A-share run follow-up now use a shared task-status hook backed by the existing task SSE stream.

## Changed Files

- `frontend/src/hooks/useTaskStatus.ts`
- `frontend/src/hooks/useTopicDetailsPrefetch.ts`
- `frontend/src/hooks/useGroupDataLoaders.ts`
- `frontend/src/hooks/useTopicFileActions.ts`
- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/components/TopicCard.tsx`
- `frontend/src/components/DailyTopicAnalysisPanel.tsx`
- `frontend/src/components/GroupFileAnalysisPanel.tsx`
- `frontend/src/components/StockTopicAnalysisPanel.tsx`
- `frontend/src/components/AShareAnalysisPanel.tsx`

## Verification Results

- `npm run build` in `frontend`: passed after clearing stale `.next` cache once.
- Final build route sizes: `/groups/[groupId]` First Load JS `206 kB`; `/groups/[groupId]/columns` First Load JS `173 kB`.
- `uv run python -m unittest tests.test_task_routes_helpers tests.test_api_smoke`: passed, 7 tests.
- Static check: high-priority target components no longer contain local `setInterval`/`pollFileTask` task polling; the only target-path `getTask` call is inside shared `useTaskStatus` for terminal task detail.
- HTTP smoke: `/` on the already running dev server returned `200`.
- Group-page HTTP smoke against the already running dev server returned `500` due to stale Next chunk resolution (`Cannot find module './548.js'`). A temporary `next start -p 3062` also surfaced the same chunk-resolution issue even though the chunk files existed, so rendered browser smoke remains blocked by local Next runtime/cache state rather than frontend compile/type errors.
