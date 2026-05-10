# 任务列表入口与残留任务处理

## Goal

在现有任务日志浮窗中增加任务列表入口，帮助定位并停止残留的 `pending` / `running` 任务，解决创建采集或同步任务时只看到冲突 toast、却找不到占用任务的问题。

## Scope

- 复用现有任务 API：`GET /api/tasks`、`POST /api/tasks/{task_id}/stop`。
- 不新增数据库表，不改变任务状态语义。
- 前端只覆盖任务浮窗、采集入口、文件下载入口和 API 错误透传。
- 不处理任务删除、自动过期和后端锁清理策略。

## Docs Checked

- `AGENTS.md`

## Implementation

- `TaskDock` 增加 `日志` / `任务` 视图切换。
- 新增 `TaskListCompact`，支持当前群组/全部任务切换、运行中优先排序、自动刷新、手动刷新和停止任务。
- `apiClient.request()` 抛出 `ApiClientError`，保留 `error.message`，额外携带 `status` 与 `detail`。
- 采集和文件下载入口识别 409 任务冲突，提示占用任务 ID，并打开任务列表视图。
- 单文件下载任务纳入同组 ingestion 锁，并在任务列表中显示为“单文件下载”。

## Verification

- `cd frontend && npx tsc --noEmit --pretty false`
- `cd frontend && npx eslint src/components/TaskDock.tsx src/components/TaskPanel.tsx src/components/TaskLogViewer.tsx src/components/TaskListCompact.tsx src/lib/api.ts src/hooks/useCrawlActions.ts src/hooks/useDownloadActions.ts`
- `python -m pytest tests/test_ingestion_helpers.py tests/test_task_runtime_helpers.py tests/test_task_routes_helpers.py`
- `python -m pytest tests/test_file_routes_helpers.py tests/test_task_runtime_helpers.py tests/test_task_routes_helpers.py`

## Status

Completed on 2026-05-10.
