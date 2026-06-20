# 任务启动模块深化计划

日期：2026-06-20

## 背景

当前任务系统已经有 `backend/services/workflow_registry.py` 记录工作流的任务类型、群组作用域、锁类型和取消能力，但多个路由和服务仍然直接拼接 `task_type`、`metadata`、锁检查和 `enqueue_runtime_task` 调用。结果是同一类启动语义分散在路由层、文件工作流服务和脚本里，后续扩展任务可见性、取消语义或任务入口时容易漏改。

本计划先把任务启动深化成一个小而稳定的服务接口，让调用方表达“我要启动哪个工作流”，而不是重复知道底层 task runtime 的细节。

## 目标

- 新增统一任务启动服务，封装普通任务和群组采集/同步任务的创建、锁冲突处理、入队和标准响应。
- 让现有路由辅助函数、文件工作流服务和主要分析任务入口逐步改用该接口。
- 保持现有 HTTP 响应、任务类型、metadata、锁语义、取消语义和日志语义不变。
- 给任务启动接口补 focused tests，避免以后新增工作流时绕过 registry 或破坏冲突响应。

## 非目标

- 不改 PostgreSQL schema，不执行 DDL。
- 不改任务运行表、任务状态机、日志存储或取消实现。
- 不改文件下载器内部下载逻辑。
- 不改 AI 分析 prompt、模型调用语义或前端 UI。
- 不把所有脚本一次性重构完；脚本迁移只处理低风险入口，剩余项记录为后续工作。

## 关键约束

- 采集/同步冲突仍返回 `409`，字段保持 `message`、`task_id`、`type`、`status`。
- 标准启动响应保持 `{"task_id": "...", "message": "任务已创建，正在后台执行"}`。
- 群组作用域任务的 `group_id` 仍写入 task metadata。
- `workflow_registry.py` 仍是工作流任务类型、锁类型和可取消能力的权威来源。
- 服务层不能依赖 route handler；route handler 可以把服务层异常转为 HTTP 异常。

## 实施步骤

1. 建立计划基线
   - 新增本文档。
   - 记录当前 dirty state，计划文档单独验证和提交。

2. 新增任务启动服务
   - 新增 `backend/services/task_launch.py`。
   - 封装普通任务启动、采集/同步任务启动、冲突详情构造和标准响应。
   - 保留 `backend/routes/ingestion_helpers.py` 的对外函数名，但改为委托服务层，降低路由层细节。
   - 新增 focused unit tests。

3. 迁移文件工作流入口
   - 让 `backend/services/file_workflow_service.py` 使用任务启动服务。
   - 移除服务层对 route helper 和未使用 `BackgroundTasks` 的依赖。
   - 保持文件收集、下载、AI 分析、总结任务的 response shape 不变。

4. 迁移分析类任务入口
   - 优先迁移当前手写 `create_task`/`enqueue_runtime_task` 的路由辅助函数：
     - `backend/routes/daily_stock_concept_routes.py`
     - `backend/routes/daily_analysis_routes.py`
     - `backend/routes/stock_topic_analysis_routes.py`
     - `backend/routes/a_share_routes.py`
     - `backend/routes/columns_routes.py`
     - `backend/routes/crawl_routes.py`
   - 每个文件只改启动样板，不改业务函数参数、任务执行函数或响应字段。

5. 验证与收口
   - 运行 focused backend tests。
   - 运行 `uv run python scripts\scan_postgres_compat_debt.py`。
   - 运行 full unittest discover；如外部依赖阻塞，记录具体阻塞条件。
   - 做一次实现后 review，确认没有扩大范围。
   - 分片提交实现。

## 验证命令

优先按变更面运行：

```powershell
uv run python -m py_compile backend/services/task_launch.py backend/services/workflow_registry.py backend/services/task_runtime.py
uv run python -m unittest tests.test_task_launch -v
uv run python -m unittest tests.test_file_routes_helpers tests.test_crawl_routes_helpers tests.test_columns_routes_helpers tests.test_daily_stock_concept_routes_helpers tests.test_daily_analysis_routes_helpers tests.test_stock_topic_analysis_routes_helpers tests.test_a_share_routes_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
```

## 完成标准

- 新任务启动服务存在并有 focused tests。
- 已迁移的任务入口不再手写重复的标准响应、metadata 组装和入队样板。
- 现有 task type、group metadata、冲突响应和任务入队行为保持兼容。
- 所有可运行验证通过，或明确记录外部依赖型跳过项。
- 实现以窄提交收口，未纳入无关 dirty 文件。

## 进度记录

- 2026-06-20：创建计划文档，准备进入服务层实现。
- 2026-06-20：新增 `backend/services/task_launch.py`，迁移 ingestion helper、文件工作流入口和主要路由任务入口。
- 2026-06-20：保留既有任务响应、群组 metadata、采集锁冲突 409 详情和 columns 创建后标记 running 的行为。
- 2026-06-20：验证通过：
  - `uv run python -m py_compile backend\services\task_launch.py backend\routes\daily_stock_concept_routes.py backend\routes\daily_analysis_routes.py backend\routes\stock_topic_analysis_routes.py backend\routes\a_share_routes.py backend\routes\columns_routes.py backend\routes\crawl_routes.py`
  - `uv run python -m unittest tests.test_task_launch tests.test_ingestion_helpers tests.test_file_routes_helpers tests.test_daily_stock_concept_routes_helpers tests.test_daily_analysis_routes_helpers tests.test_stock_topic_analysis_routes_helpers tests.test_a_share_routes_helpers tests.test_columns_routes_helpers tests.test_crawl_routes_helpers -v`
  - `uv run python scripts\scan_postgres_compat_debt.py`
  - `uv run python -m unittest discover -s tests`
