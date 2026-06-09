# Project Architecture Roadmap

## Goal

Keep ZsxqCrawler evolving as a reliable group-level data workbench, not a pile of crawler scripts and one-off analysis panels.

The current architecture direction is:

1. Knowledge Planet APIs and local files are ingestion sources.
2. PostgreSQL `zsxq_core` is the only structured data source of truth.
3. FastAPI routes expose bounded product workflows.
4. Backend services hold business logic and AI/reporting logic.
5. The Next.js frontend presents group-scoped workbenches.
6. Other projects read durable data through read-only PostgreSQL access.

## Current Architecture

### Runtime Layers

- `backend/main.py`: FastAPI application factory and route registration.
- `backend/routes/`: HTTP API boundaries. Routes should validate request shape, start tasks, call services, and return product-facing responses.
- `backend/services/`: Workflow and domain logic, including crawl orchestration, task runtime, AI analysis, A-share analysis, export, diagnostics, and reporting.
- `backend/storage/`: PostgreSQL access, schema definitions, task persistence, account storage, file/topic storage, and compatibility boundaries.
- `backend/crawlers/`: Knowledge Planet topic and file crawling clients.
- `frontend/src/app/`: Next.js route entrypoints.
- `frontend/src/components/`: Group workbench panels and reusable UI surfaces.
- `frontend/src/hooks/`: Frontend workflow state and API action coordination.
- `scripts/`: Operational commands for schema, access, migration, probes, audits, and reports.

### Data Ownership

Structured records live in PostgreSQL schema `zsxq_core`.

- Topics, comments, articles, files, tasks, accounts, AI reports, file AI analyses, A-share analysis outputs, and daily stock concepts belong in `zsxq_core`.
- `output/databases/{group_id}/downloads/` stores downloaded file bytes.
- `output/databases/{group_id}/images/` stores disposable image caches.
- Legacy `zsxq_*` schemas and `zsxq_public` are migration artifacts, not supported runtime interfaces.

Schema changes should go through:

```powershell
uv run manage-postgres-core-schema --apply
```

Runtime code should not execute DDL by default.

### Product Surfaces

The main user-facing surface is the group detail workbench at `/groups/[groupId]`.

Stable group-level areas:

- Topic browsing and topic detail drilldown.
- Crawl and sync actions.
- File management, download, retry, and file AI analysis.
- Daily topic analysis.
- Daily stock concept extraction.
- A-share recommendation and Tongdaxin export workflows.
- Task status, task logs, and long-running job visibility.

The root page should remain a group selector and overview entrypoint. New user workflows should normally land inside the group workbench unless they are truly global.

## Architectural Boundaries

### PostgreSQL First

New structured data should use explicit PostgreSQL SQL and table specs in `backend/storage/postgres_core_schema.py`.

Do not reintroduce SQLite runtime behavior. `backend/storage/db_compat.py` should remain a narrow PostgreSQL connection and row-adaptation compatibility layer, not a SQL translation engine.

### Separate Similar Workflows

Some workflows share helpers but must stay separate at the product boundary:

- A-share recommendation pool is a multi-day ranking and statistics workflow.
- Daily stock concept extraction is a same-day explanatory workflow.
- Daily topic analysis is a report workflow over topic material.
- File AI analysis is a document/file workflow.

These workflows may share low-level helpers such as stock normalization, date parsing, topic loading, JSON parsing, AI config, and response extraction. They should keep separate routes, tables, task types, and UI surfaces.

### Task Runtime As The Coordination Layer

Long-running work should go through the task system.

Task responsibilities:

- Create and persist task state.
- Expose logs and status to the frontend.
- Support cancellation where the backend owns a cancellable crawler or worker.
- Enforce ingestion locks for high-risk shared write paths.
- Keep frontend panels from inventing one-off polling semantics.

When adding a long-running workflow, first decide its task type, group scope, lock domain, cancellation behavior, and verification command.

### Frontend Workbench Discipline

The group page should stay readable as a workbench:

- Page-level state belongs near `/groups/[groupId]` and shared hooks.
- Workflow-specific state belongs inside the relevant panel or hook.
- The right-side action area should be a launcher/status companion, not the only place where core work happens.
- Large panels should be split only when there is a clear state or responsibility boundary.
- Reusable dialogs must not drift into different behavior from their page-level equivalents.

## Roadmap

### Stage 1: Stabilize The Data Foundation

Goal: make `zsxq_core` the boring, trusted base layer.

- Keep runtime writes on explicit PostgreSQL SQL.
- Keep schema setup in `manage-postgres-core-schema`.
- Preserve content table semantics:
  - one logical row per topic for `talks`, `questions`, `answers`, and `articles`;
  - snapshot keys for `latest_likes`, `like_emojis`, and `user_liked_emojis`;
  - append/history semantics for `likes`.
- Continue reader/writer role verification before sharing DSNs with other projects.
- Run PostgreSQL smoke/probe scripts after storage or schema changes.

Recommended verification:

```powershell
uv run python scripts/scan_postgres_compat_debt.py
uv run python -m unittest tests.test_db_compat tests.test_postgres_core_schema tests.test_zsxq_database_helpers tests.test_zsxq_file_database_helpers -v
```

### Stage 2: Make Task Runtime A Product Contract

Goal: one task model across crawl, download, analysis, export, and sync.

- Document task types and lock domains.
- Keep ingestion tasks grouped by `group_id` and shared write risk.
- Route all long-running frontend workflows through task creation, status, logs, and cancellation where possible.
- Prefer a small shared task UI pattern over panel-specific polling code.

Recommended verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
```

### Stage 3: Refine The Group Workbench

Goal: make `/groups/[groupId]` the clear operating console.

- Keep tab boundaries stable: topics, files, daily analysis, A-share/stock workflows, and settings/actions.
- Move repeated data-loading concerns into hooks.
- Keep row-level actions deterministic.
- Avoid adding new global pages for group-scoped work.
- Use route-level or panel-level smoke checks after UI changes.

Recommended verification:

```powershell
npm --prefix frontend run build
```

If global lint is blocked by unrelated existing issues, run focused TypeScript or ESLint checks for touched files and record the blocker.

### Stage 4: Consolidate AI Workflow Infrastructure

Goal: share AI plumbing without merging business outputs.

- Centralize provider/model config usage.
- Share JSON schema response handling where practical.
- Keep prompt versions and output tables workflow-specific.
- Keep file attachment, image, and transcription capability checks proof-first.
- Treat daily reports, file analysis, stock concepts, and A-share extraction as separate products.

Recommended verification:

```powershell
uv run python -m unittest tests.test_daily_topic_analysis_service_helpers tests.test_daily_stock_concept_service_helpers tests.test_file_ai_analysis_service_helpers tests.test_a_share_analysis_service_helpers -v
```

### Stage 5: Publish A Stable Reader Contract

Goal: make ZsxqCrawler useful as an upstream data system.

- Maintain `docs/postgres_core_reader_usage.md` as the public read contract.
- Mark supported reader tables and avoid exposing legacy schemas.
- Keep read-only verification commands current.
- Add examples for common downstream analysis queries when they stabilize.

Recommended verification:

```powershell
uv run verify-postgres-reader-access --dsn "<reader-dsn>"
uv run generate-postgres-status-report --output docs\postgres_status_report.md
```

## Change Rules

- Keep feature changes narrow and group-scoped unless a global workflow is explicitly required.
- Do not mix data migrations, UI redesigns, and analysis semantics in one change.
- Prefer docs-first for storage, task, schema, or workflow-boundary changes.
- Stage and commit only files related to the coherent slice being finished.
- When storage and UI disagree, inspect the live data path before changing product behavior.

## Active Follow-Ups

- Keep `README.md` as the operational quick-start and link to this roadmap for architecture context.
- Use `docs/postgres_compat_deprecation_plan.md` for compatibility-layer cleanup.
- Use `docs/postgres_ingestion_write_order_review.md` for shared ingestion write risks.
- Use `docs/postgres_core_reader_usage.md` for downstream read access.
- Use group-workbench-specific plans only for active UI slices, then close or archive them when done.
