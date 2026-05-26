# Group Sidebar Context Actions Plan

## Goal

Make the group detail right action sidebar follow the main content tab: show topic crawling actions on the topic list tab, file download actions on the file tab, and contextual control rails on the A-share analysis and daily analysis tabs.

Add a compact collapse/expand affordance to the left group info sidebar so the main work area can use more horizontal space when needed.

## Scope

- Group detail page right action sidebar.
- Main tabs: topic list, file list, A-share analysis, and daily analysis.
- Put contextual control rails inside each tab content area below the tab list.
- Add a first-pass A-share analysis action rail without changing API behavior.
- Add a first-pass daily summary action rail without changing API behavior.
- Add left group info sidebar collapse/expand without changing data loading or tab behavior.

## Docs Checked

- `AGENTS.md`
- `docs/crawl_time_range_api_plan.md`

## Execution Steps

1. Derive the right sidebar action mode from the main page tab.
2. Remove the sidebar's internal crawl/download tab switch.
3. Preserve existing crawl and download controls inside their respective contextual panels.
4. Verify the frontend build.
5. Move daily summary date, report generation, concept extraction, and view filters into a right-side control rail.
6. Move A-share chart filters, run controls, TDX import, and advanced maintenance into a right-side control rail.
7. Move topic and file action panels inside their own tab content rows, below the main tab list.
8. Add a page-local collapsed state for the left group info sidebar.
9. Verify build and one rendered collapse/expand smoke path.

## Progress

- Topic list tab now maps the right sidebar to topic crawling actions.
- File tab now maps the right sidebar to file download actions.
- Daily analysis now renders its own right-side control rail.
- A-share analysis now renders its own right-side control rail.
- Topic and file action panels now sit below the tab list inside their tab content rows.
- Left group info sidebar can now collapse to a narrow icon rail and expand back in place.

## Changed Files

- `frontend/src/app/groups/[groupId]/page.tsx`
- `frontend/src/components/GroupActionPanel.tsx`
- `frontend/src/components/AShareAnalysisPanel.tsx`
- `frontend/src/components/DailyTopicAnalysisPanel.tsx`
- `frontend/src/components/GroupSidebar.tsx`
- `docs/group_sidebar_context_actions_plan.md`

## Verification Results

- `npm run build` in `frontend`: passed.
- Browser plugin validation attempted twice against `http://localhost:3060/groups/51111112855254`, but navigation timed out before a DOM snapshot was available.
- HTTP check for the same page returned `200 OK`.
- Daily sidebar first pass: `npm run build` in `frontend`: passed.
- Playwright screenshot check was attempted, but the local `playwright` module could not be resolved from the frontend workspace.
- A-share sidebar first pass: `npm run build` in `frontend`: passed.
- Topic/file tab-contained sidebar pass: pending verification.
- Left sidebar collapse pass: `npm run build` in `frontend`: passed.
- Browser plugin collapse/expand smoke was attempted twice against `http://localhost:3060/groups/51111112855254`, but navigation timed out before interaction state could be captured.
- HTTP check for the same page returned `200 OK`.
