# 架构优化跟进实施计划

日期：2026-06-20

## 背景

上一轮已经完成 AI 兼容调用、文件下载 body transfer、topic material、前端 task launcher、脚本 task launch 下沉五个优化片。重新扫描后，剩余高价值点集中在：route 仍保留部分重复 task runner、文件下载器仍承担多个 runner 职责、前端 task stream 与日志查看重复连接、个股话题分析接口仍偏宽、根目录 scratch 文件治理。

## 目标

- 让 HTTP route 成为 `workflow_task_launch` 的 adapter，task lifecycle 只在服务模块维护。
- 继续深化文件下载模块，把 time collection / database download 这种 runner 逻辑从 `ZSXQFileDownloader` 中收窄到独立模块接口。
- 建立前端 task stream hook，集中 SSE、fallback polling、log/status reducer、terminal callback。
- 为个股话题分析建立 runner interface，保留现有路由和响应形状，但让调用方更少知道内部 search/AI/store seam。
- 建立 scratch artifact path guardrail，并把当前根目录 ignored stock-analysis 临时文件迁移到 `output/scratch/` 下。

## 非目标

- 不改 PostgreSQL schema，不执行运行时 DDL。
- 不改 AI prompt、业务输出 JSON shape、任务类型、任务状态语义或前端产品入口。
- 不删除真实下载文件，不清理 `output/databases/{group_id}/downloads/`。
- 不删除用户未明确纳入本计划的未跟踪文件；本计划仅迁移 `.gitignore` 已忽略的根目录 `tmp_stock_analysis_*` 临时文件。
- 不重做 group workbench UI。

## 实施步骤

### P1：Routes 复用 `workflow_task_launch`

1. 扩展 `workflow_task_launch` 支持 route 需要的 request fields。
2. 将 A-share、daily topic、daily stock concept route 的 task 创建/runner 逻辑下沉到该模块。
3. Route 保留 Pydantic request model 和 HTTP error mapping。
4. 更新 route tests，使它们验证 adapter 调用服务 module，而不是重复测试 route 私有 runner。

### P2：文件下载 runner 深化

1. 先抽低风险 runner：database-row download 或 time collection 中已经有清晰 target/result 的部分。
2. `ZSXQFileDownloader` 保持 public facade，委托给新 runner。
3. focused downloader tests 只覆盖新 runner interface 和 facade 兼容。

### P3：前端 task stream

1. 新增 `frontend/src/hooks/useTaskStream.ts`。
2. 迁移 `useTaskStatus` 复用新 stream interface。
3. 迁移 `TaskLogViewer` 复用新 stream，保留现有视觉和 stop 行为。
4. 运行 frontend build。

### P4：个股话题分析 runner

1. 新增 runner module，导出 analyze one / analyze batch / answer question interface。
2. `stock_topic_analysis_service.py` 保留兼容 wrapper，内部委托 runner。
3. focused stock topic tests 验证 wrapper 和 runner 行为一致。

### P5：Scratch artifact guardrail

1. 新增脚本可复用的 artifact path helper。
2. 迁移活跃 stock-analysis runner scripts 的输出路径。
3. 将根目录已忽略的 `tmp_stock_analysis_*` 文件移动到 `output/scratch/root-stock-analysis-temp-archive/`。
4. 补 guardrail 测试，避免未来默认写回根目录。

## 验证

按片运行 focused tests；最终运行：

```powershell
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
```

## 完成标准

- 五个候选均完成最小可验证优化。
- 每片独立窄提交。
- 最终工作区干净。

## 进度记录

- P1 已完成：A-share、daily topic、daily stock concept route 的 task 创建/runner 逻辑已统一委托 `workflow_task_launch`，route 只保留 request/error adapter；focused tests 36 个通过，route 残留 lifecycle 关键词扫描无命中。
- P2 已完成：数据库文件下载 runner 已抽到 `backend/crawlers/file_database_download_runner.py`，`ZSXQFileDownloader.download_files_from_database` 保持 facade；focused database download tests 15 个通过，相关模块 py_compile 通过。
- P3 已完成：新增 `useTaskStream` 统一 SSE、状态 fallback polling、日志恢复和 terminal callback；`useTaskStatus` 与 `TaskLogViewer` 已复用该 hook；`npm --prefix frontend run build` 通过且无 lint/type 警告。
