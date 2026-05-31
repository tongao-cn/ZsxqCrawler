# AGENTS.md

AI coding agent operating guidelines for this repository. These rules are intended to reduce common LLM coding mistakes while keeping execution practical, and are written to be reusable across projects.

Use judgment for trivial tasks. These guidelines bias toward correctness, clarity, and minimal diffs over speed.

## Project Snapshot

- This is a Knowledge Planet data crawler and group-level workbench for topic sync, file downloads, AI analysis, daily stock concepts, and A-share research workflows.
- Python backend code lives under `backend/`; operational entrypoints live in `main.py`, `backend/main.py`, `scripts/`, and `tests/`.
- The Next.js frontend lives under `frontend/`; run frontend commands with `npm --prefix frontend ...`.
- Use `uv run python -m backend.main` or `uv run zsxq-api` for the backend. Root `main.py` is a compatibility entrypoint.
- PostgreSQL schema `zsxq_core` is the structured data source of truth. Runtime code should not execute DDL by default; use `uv run manage-postgres-core-schema --apply` for schema setup.
- Local secrets and machine-specific config belong in `.env` or `config.toml`; do not echo secret values in responses or logs.
- Operational quick start lives in `README.md`; durable architecture and workflow boundaries live in `docs/project-architecture-roadmap.md`.

## 1. Think Before Coding

Do not silently guess.

- State assumptions when they materially affect the implementation.
- If the request is ambiguous and there are multiple reasonable interpretations, surface them instead of picking one silently.
- If a simpler or safer path exists, say so before implementing.
- If you are blocked by missing requirements, ask a short clarifying question instead of inventing behavior.

## 2. Prefer Simple Solutions

Implement the smallest change that fully solves the requested problem.

- Avoid over-engineering. Only make changes that are directly requested or clearly necessary; keep solutions simple and focused.
- Do not add features, options, abstractions, or configurability that were not requested.
- Do not generalize for hypothetical future use.
- Avoid introducing new layers, helpers, or patterns for one-off logic.
- Do not add defensive error handling, fallbacks, validation, feature flags, or backwards-compatibility shims for impossible internal states. Trust internal code and framework guarantees; validate at system boundaries such as user input, files, databases, external APIs, and LLM output.
- If the same result can be achieved with materially less code, prefer the shorter version.

## 3. Make Surgical Changes

Keep diffs tightly scoped to the task.

- Touch only files and lines that are needed for the requested outcome.
- Do not refactor adjacent code unless the task requires it.
- Do not add docstrings, comments, type annotations, or other cleanup to code you did not otherwise need to change. Add comments only where the logic is not self-evident.
- Match the surrounding style and conventions of the repository.
- Do not remove unrelated dead code, comments, or formatting noise just because you noticed it.
- Clean up only issues directly created by your own change, such as unused imports you introduced.
- When the requested change removes code and you are certain something is unused, delete it cleanly instead of leaving compatibility hacks such as unused renamed variables, re-exports, or "removed" comments.

## 4. Work Backward From Verification

Define success in a way that can be checked.

- For bug fixes, prefer reproducing the issue first, then fixing it.
- For new behavior, prefer adding or updating tests when the repo already uses tests.
- For refactors, preserve behavior and verify before and after when practical.
- End work by running the smallest meaningful verification available, such as targeted tests, lint, build, or a focused manual check.
- If verification fails because of your change, keep fixing or clearly state the blocker.
- If verification fails for an unrelated pre-existing reason, record the command, evidence, and residual risk instead of silently fixing unrelated code.

For multi-step tasks, think in this format:

1. Change
2. Verify
3. Repeat until the requested outcome is satisfied

### 本项目验证

选择验证命令时优先按改动面做最小检查；涉及架构、存储、任务运行时或工作流边界时，先查 `docs/project-architecture-roadmap.md` 的对应建议。

- 后端基础: `uv run python -m pytest tests/test_xxx.py -x -q`
- 后端语法: `uv run python -m py_compile backend/path/to/file.py`
- 前端基础: `npm --prefix frontend run build`
- 前端开发服务: `npm --prefix frontend run dev`
- PostgreSQL schema / 权限: `uv run manage-postgres-core-schema --apply`、`uv run manage-postgres-core-access --apply`
- PostgreSQL smoke: `.\scripts\run_postgres_core_smoke.ps1` 或 `.\scripts\run_postgres_runtime_cutover_smoke.ps1`

如果 Docker、PostgreSQL、外部 API、Cookie 或 LLM 密钥不可用，记录未运行的命令和缺失条件，不要伪造验证结果。

### 本项目测试资产管理

- 新增测试优先放在 `tests/` 中与被测模块同主题的既有文件，避免为一次性排查新增永久测试文件。
- 一次性 probe、audit、smoke 脚本优先放在 `scripts/`，并在完成后保留为明确的运维命令或删除临时产物。
- 修测试失败时先判断失败代表代码回归、测试过时，还是外部环境缺失；不要只机械更新期望值。

### 本项目架构边界

- 新结构化数据写入 PostgreSQL `zsxq_core`，schema 定义集中在 `backend/storage/postgres_core_schema.py`。
- 不要重新引入 SQLite 运行时行为；`backend/storage/db_compat.py` 应保持为窄兼容层。
- 长任务应走任务系统，明确 task type、`group_id` 范围、锁域、取消语义和前端轮询方式。
- 主要用户界面是 `/groups/[groupId]` 工作台；除非明确是全局能力，新工作流通常不要新增全局页面。
- A-share 推荐池、每日股票概念提取、每日话题分析、文件 AI 分析是不同产品工作流，可以共享底层工具，但保持路由、表、任务类型和 UI 边界清晰。
- 当 UI 和存储表现不一致时，先查真实后端/数据库路径，再改产品行为。

### 本项目 AI 与批处理运行

- 用户要求“使用数据库话题”做分析时，不要重新爬取。
- 股票话题分析中，`MAX_BATCH_STOCK_ANALYSIS_WORKERS` 是股票级并发；单只股票内部的 AI 请求仍按批次顺序执行。
- `MAX_ANALYSIS_TOPICS_PER_CALL` 控制单次 AI 调用包含的话题片段数。200+ 片段的重股票应缩小股票组或降低批量，避免 429、503 和超时。
- 批处理失败后优先保留 checkpoint 并重试失败项；汇报缺口数量前重新查询当前数据。
- Windows PowerShell 可能使用 GBK 控制台输出；长时间脚本日志避免 emoji，必要时做 GBK-safe 输出。

### 本项目工作区治理

- 新增运行产物、临时验证文件或清理目录前，先查 `git status --short`，确认不会碰到其他 agent 或用户的未提交改动。
- 不要在仓库根目录新增散落的临时 JSON、日志或导出文件；临时产物使用 `tmp/` 或被忽略的 `output/` 子目录，并在完成后清理或说明保留原因。
- `output/databases/{group_id}/downloads/` 可能包含真实下载文件，不要在未明确确认前清理。
- `output/databases/{group_id}/images/` 是可再生图片缓存，但清理前仍要确认没有正在运行的任务。
- `.pytest_cache/`、`__pycache__/`、`frontend/.next/` 是可再生临时产物；不要把这些目录加入提交。

### 本项目命令环境

- 默认 shell 是 Windows PowerShell。
- Python 命令优先使用 `uv run ...`，确保与项目环境一致。
- 不使用 `python -` 传递多行脚本；短脚本用 `python -c`，多行逻辑使用临时 `.py` 文件。
- 前端命令从仓库根目录执行时使用 `npm --prefix frontend ...`。

## 5. Communication

Keep communication concise and useful.

- Share short progress updates during longer tasks.
- Mention important assumptions, tradeoffs, and risks.
- If you notice unrelated problems, mention them briefly instead of fixing them without permission.

## 6. Safety Rails

- Never overwrite or revert user changes unless explicitly asked.
- Do not make destructive changes outside the requested scope.
- When working in an existing codebase, preserve established patterns unless the user asks for a redesign.
- Never print, copy, or modify secrets from `.env`; use `.env.example` for documentation or configuration references. If the user explicitly asks you to write local config, do not echo secret values back in the response.
- Do not reformat whole files or projects unless requested or required by the touched toolchain.
- Do not reorder unrelated imports, update lockfiles, or clean unrelated dead code unless the task requires it.

## 7. Git And Multi-Agent Hygiene

- Commit after each logically coherent and verified change. Do not accumulate unrelated changes before committing. Each commit should be a single self-contained step that could be reverted independently.
- Stage and commit only your own changes; do not include unrelated user edits or changes made by other agents.
- Assume other agents may be working in the same repository at the same time. Before editing, staging, or committing, check the current worktree state, keep your diff scoped, avoid overlapping ownership when possible, and never overwrite or revert changes you did not make.
- If another agent has changed a file you also need, inspect the current diff before editing and make the smallest compatible change. If ownership is unclear or the changes conflict, pause and ask instead of guessing.
- Before staging or committing, re-check `git status --short` and review your own diff so you do not accidentally include concurrent work.

## 8. Documentation-First Workflow

Use docs according to task risk and scope.

Keep this file as an execution guide for cross-task rules and common entrypoints. Put durable module details, research conclusions, and long-lived operational notes under `docs/` instead of expanding AGENTS.md.

本项目文档入口:
- 快速开始与运行入口: `README.md`
- 架构与边界: `docs/project-architecture-roadmap.md`
- PostgreSQL 只读契约: `docs/postgres_core_reader_usage.md`
- 活跃计划: `docs/*.md`
- 历史计划与报告: `docs/archive/`

Fast path is for small localized work, such as wording fixes, link fixes, code explanations, command inspection, narrow test repairs, and single-file bug fixes that do not change public APIs, durable semantics, or long-lived project rules.

Fast path:

- Read only the directly relevant docs when needed.
- Do not create a plan just to satisfy process.
- Make the smallest viable change and run the smallest meaningful verification, or explain why verification was not run.

Plan path is for higher-risk work: changes that alter public APIs, durable runtime semantics, architecture boundaries, configuration semantics, research methodology, data/storage contracts, crawler behavior, AI output semantics, or anything needing a reusable verification or rollback trail. Multi-file changes do not automatically require plan path when the scope is still local, low-risk, and easy to verify.

Plan path:

- For plan-path work, start from `README.md` and `docs/project-architecture-roadmap.md`, then read only directly relevant reference, guide, or plan documents.
- Reuse an existing active plan, roadmap, backlog, or reference page when it fits; create a new short kebab-case plan only when durable tracking is needed and no existing doc fits.
- Record the minimum useful plan: goal, scope, constraints, docs checked, execution steps, verification plan, progress, changed files, and verification results.
- Implement the smallest viable change against the plan, and update the plan first if scope or design changes.
- If docs conflict with code or with each other, pause and surface the conflict.

Document lifecycle:

- Keep planning docs active and finite. After a plan-path task is completed, update its status and either keep it only if it still guides active work, archive it, or move durable conclusions into stable overview, reference, or guide docs.
- Avoid creating new docs when an existing active plan, backlog, or reference page can be updated cleanly.

Completion for plan-path work requires checked docs, recorded verification, and a final response that names the docs checked and the verification run. If a tracked plan was created or reused, update it and name it in the final response. If unsure what to run, use the architecture roadmap or the smallest meaningful local verification.

## Practical Default

When in doubt: clarify ambiguity, choose the fast path or plan path by risk, check relevant docs, make the smallest viable change, verify it, and record the outcome.
