# 架构优化全量实施计划

日期：2026-06-20

## 背景

任务启动模块已经完成深化，路由和文件工作流里重复的任务创建、入队、群组 metadata 和采集锁冲突处理已经收敛到 `backend/services/task_launch.py`。重新扫描后，下一批主要浅模块集中在 AI 兼容调用、文件下载执行器、topic material 读取、前端 task handle，以及脚本绕过服务层调用 route handler。

本计划覆盖这 5 个方向，但按小片推进。每一片只移动一个清晰 seam，保持现有产品行为、任务状态、存储 schema、prompt 输出语义和前端入口不变。

## 目标

- 建立一个小接口的 AI 兼容调用模块，集中 Responses / Chat Completions 调用、文本提取、JSON schema response format 和 retry 分类。
- 从 `ZSXQFileDownloader` 中抽出至少一个高收益内部模块，让下载 URL 或传输写入逻辑变成可独立测试的深模块。
- 建立 topic material 读取/组装接口，减少每日话题、每日股票概念、A 股分析和个股话题之间的重复读取逻辑。
- 建立前端 task handle hook，收敛 task_id、冲突提示、toast、完成回调和 task dock 打开逻辑。
- 把脚本入口从 route handler 下沉到 service-level orchestration，保持 HTTP route 作为 adapter。
- 每片都有 focused tests 或构建验证，最终跑全量后端测试和前端 build。

## 非目标

- 不改 PostgreSQL schema，不执行运行时 DDL。
- 不改 AI prompt 文本、prompt version、结构化输出 schema 或业务表语义。
- 不改真实下载协议、下载重试策略、停止语义或落盘目录。
- 不重做 `/groups/[groupId]` 的布局或新增全局页面。
- 不删除 legacy crawl/source fallback；只收敛可证明重复的调用样板。
- 不把 unrelated dirty 文件纳入提交。

## 模块设计原则

- 每个新模块都要有小接口，复杂实现留在模块内部。
- 对第三方 AI provider 这种 true external dependency，只在模块内部建立可测试 adapter seam；业务调用方不感知 OpenAI SDK 细节。
- 迁移调用方时先保留原有 thin wrapper 或别名，等测试覆盖新 interface 后再删除重复实现。
- 旧测试若仍描述外部行为则保留；只删除明显测试过内部旧样板、且新 interface 已覆盖的测试。

## 实施步骤

### P1：AI 兼容调用模块

1. 新增 `backend/services/ai_client.py`，提供：
   - `AITextRequest`
   - `AIJsonSchema`
   - `call_ai_text(...)`
   - `extract_response_text(...)`
   - `chat_json_schema_response_format(...)`
   - `responses_json_schema_text_format(...)`
   - `is_retryable_ai_error(...)`
2. 先迁移已拆分较好的 `daily_topic_analysis_ai.py` 使用新模块。
3. 迁移 `file_ai_analysis_service.py`、`daily_stock_concept_service.py`、`a_share_analysis_ai.py`、`stock_topic_analysis_service.py` 的重复 OpenAI 调用。
4. 保持各业务服务自己的 prompt、model 选择、reasoning effort 和 parse/save 逻辑。
5. 补 `tests/test_ai_client.py`，并更新既有 AI 服务 helper tests。

### P2：文件下载执行器窄拆分

1. 不大拆 `ZSXQFileDownloader`，先抽内部下载传输接口：
   - 目标候选：HTTP 响应到临时文件写入、进度统计、停止检查、size mismatch 结果。
2. 新模块优先放在 `backend/crawlers/file_download_transfer.py` 或新增相邻 helper，保持 `ZSXQFileDownloader.download_file(...)` 外部行为不变。
3. 补 focused helper tests，不触碰真实网络下载。

### P3：Topic material 读取接口

1. 新增或深化 `backend/services/topic_material.py`。
2. 先提供只读接口：按 group/date/range 读取 topic、talk text、comments、images 的标准 payload。
3. 迁移 `daily_stock_concept_service.py` 复用 `daily_topic_analysis_topics.py` / 新 material 接口，避免直接 import 每日报告 service 的 private wrapper。
4. 后续再迁移 A 股分析和个股话题搜索里的重复 payload shaping。

### P4：前端 task handle hook

1. 新增 `frontend/src/hooks/useTaskLauncher.ts` 或 `useTrackedTask.ts`。
2. 先迁移 crawl/download 两个重复度最高 hook 的 task 创建成功与冲突处理。
3. 再迁移 group file batch、stock topic batch、A-share analysis task 的 active task 设置和完成回调。
4. 保持 `TaskLogViewer`、task dock 和 route response shape 不变。

### P5：脚本入口下沉到服务层

1. 为日常刷新脚本新增 service-level orchestration 函数，避免脚本直接调用 route handler。
2. 迁移：
   - `scripts/export_daily_review_topics.py`
   - `scripts/run_zsxq_topic_recommendation_refresh.py`
3. 脚本仍可复用 Pydantic request model，但不依赖 FastAPI `BackgroundTasks` 或 HTTP route adapter。
4. 补/更新脚本单测。

## 验证命令

按片运行 focused tests：

```powershell
uv run python -m py_compile backend/services/ai_client.py
uv run python -m unittest tests.test_ai_client tests.test_ai_json_utils tests.test_daily_topic_analysis_service_helpers tests.test_daily_stock_concept_service_helpers tests.test_file_ai_analysis_service_helpers tests.test_a_share_analysis_service_helpers tests.test_stock_topic_analysis_service_helpers -v
uv run python -m unittest tests.test_file_routes_helpers tests.test_crawl_routes_helpers tests.test_export_daily_review_topics_script -v
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
```

如某条验证因为外部服务、真实 PostgreSQL、OpenAI key 或前端环境阻塞，记录具体命令和阻塞条件。

## 完成标准

- 5 个方向都有已实施的最小可验证优化。
- 业务 HTTP 响应、task type、metadata、任务状态、存储 schema、AI prompt 和输出结构保持兼容。
- 新模块有 focused tests，迁移调用方的现有 tests 通过。
- 后端全量 unittest、PostgreSQL compat 扫描和前端 build 通过，或明确记录外部阻塞。
- 每个 coherent slice 都窄提交，最终 worktree 只剩用户无关改动或保持干净。

## 进度记录

- 2026-06-20：创建本计划，准备实施 P1 AI 兼容调用模块。
- 2026-06-20：完成 P1。新增 `backend/services/ai_client.py`，集中 Responses / Chat Completions 调用、响应文本提取、JSON schema format 和 retry 分类；迁移每日话题、文件 AI、每日股票概念、A 股推荐池抽取、个股话题分析调用点；新增 `tests/test_ai_client.py`，focused AI tests 通过。
- 2026-06-20：完成 P2。新增 `file_download_transfer.write_download_response_body_stream`，将下载响应体流式写入、进度回调和停止检查从 `ZSXQFileDownloader` 中抽到 transfer helper；下载器保留兼容入口；`FileDownloaderDownloadTests` 通过。
- 2026-06-20：完成 P3。新增 `backend/services/topic_material.py`，集中每日 topic material 日期解析、连接、读取和 prompt payload；每日股票概念改依赖该接口；个股话题 payload/服务改直接依赖底层 `clip_text`，不再 import 每日话题 service 私有 wrapper；focused material/stock tests 通过。
- 2026-06-20：完成 P4。新增 `frontend/src/hooks/useTaskLauncher.ts`，集中 task 创建成功 toast/callback 和 task 冲突错误处理；迁移 crawl/download action hooks；`npm --prefix frontend run build` 通过。
