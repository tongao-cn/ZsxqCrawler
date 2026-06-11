# Systematic Refactor Plan - 2026-06-11

## Purpose

Coordinate safe refactor, cleanup, and governance work for ZsxqCrawler without changing business
logic, public APIs, response shapes, config semantics, task behavior, SQL side effects, prompts, or
fallback compatibility.

This is the active plan for the next work rounds. Keep each implementation slice small, verified,
and committed independently.

## Baseline

Observed on 2026-06-11:

- `git status --short` shows only out-of-scope root `tmp_stock_analysis_*` files.
- `uv run python -m unittest discover -s tests`: 506 tests passed, 15 skipped.
- `npm --prefix frontend run build`: passed.
- `uv run python scripts\scan_postgres_compat_debt.py`: no SQLite compatibility patterns found.
- The previous `docs/module-refactor-execution-plan-20260610.md` is a completed plan and should
  remain as historical evidence, not the active execution plan.

## Guardrails

- Work directly on `main`.
- Stage and commit only files touched for the current slice.
- Do not modify root `tmp_stock_analysis_*` files unless cleanup is explicitly requested.
- Do not remove legacy or fallback behavior without proof that it is unreachable, unused, or fully
  covered by equivalent behavior.
- Add characterization tests before refactoring behavior that touches tasks, fallback paths,
  storage, crawler IO, AI output shape, config defaults, or public route responses.
- Prefer pure helper extraction, row/payload mapper extraction, and hook/presentation boundaries
  before larger module moves.

## Legacy And Fallback Register

| Area | Current role | Default action | Verification guard |
| --- | --- | --- | --- |
| Topic source `legacy` | Explicit cookie crawler path behind `topicSource=legacy` and legacy aliases | Keep | Crawl route tests and official topic tests |
| Official topic path | Default topic crawl path when configured | Keep | Official topic client tests |
| Group local fallback | Keeps group detail usable when official lookup fails | Keep | Group route helper tests |
| A-share local CSV fallback | Allows analysis to continue if PostgreSQL storage is unavailable | Keep | A-share service helper tests |
| `db_compat.py` | Narrow PostgreSQL connection and row-adaptation compatibility layer | Keep | Compatibility debt scan and storage tests |
| File downloader retry fallback | Handles retryable API, HTTP, and signed URL failures | Keep | Downloader helper tests |
| Task SSE fallback polling | Keeps frontend task status live when SSE closes or fails | Keep | Frontend build and task UI checks |

## Refactor Backlog

| Priority | Files or modules | Purpose | Risk | Verification | New tests | Legacy/fallback handling |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Root `tmp_stock_analysis_*` files | Inventory only | Low | `git status --short` | No | Preserve |
| P1 | `backend/services/file_workflow_service.py` | Extract file listing filters, pagination, row mapping, and status helpers | Medium | `py_compile`; `tests.test_file_routes_helpers` | Yes | Preserve task status, response fields, error messages, paths, and side effects |
| P2 | `backend/storage/zsxq_database.py` | Extract topic/detail row mappers and payload builders | Medium | `tests.test_zsxq_database_helpers`; PG smoke only if SQL changes | Yes | Do not change schema, `db_compat.py`, runtime DDL, or compat method names |
| P3 | `backend/storage/zsxq_columns_database.py` | Extract column topic/comment row mappers | Medium | `tests.test_zsxq_columns_database_helpers`; column service tests | Yes | Preserve commit order and return shapes |
| P4 | `backend/crawlers/topic_pagination.py`, `backend/services/crawl_service.py` | Clarify pagination and official-vs-legacy source boundaries | Medium-high | Crawl route tests; official topic tests | Yes | Isolate legacy path before considering removal |
| P5 | `backend/services/task_runtime.py`, `backend/storage/task_store.py`, `frontend/src/hooks/useTaskStatus.ts` | Reduce global task-runtime state and align frontend polling/SSE behavior | High | Task tests; frontend build; manual task smoke if UI changes | Yes | Preserve cancellation, terminal ordering, lock release, and fallback polling |
| P6 | `frontend/src/lib/api/types.ts`, `frontend/src/lib/api/*` | Split API type surface by domain while keeping compatibility facade | Medium | `npm --prefix frontend run build` | Maybe | Keep `frontend/src/lib/api.ts` exports |
| P7 | `frontend/package.json`, `pyproject.toml` | Audit suspicious direct dependencies in isolated slices | Low-medium | `npm ls`; frontend build; lock diff review | No | Do not mix dependency cleanup with behavior refactors |
| P8 | `README.md`, `docs/project-architecture-roadmap.md` | Keep docs aligned with final module boundaries and verification commands | Low | grep references; relevant tests/builds | No | Archive stale plans only when cleanup is in scope |

## First Execution Slice

Start with P1 because it has clear tests, local helper seams, and lower blast radius than crawler,
storage, or task-runtime changes.

Planned slice:

1. Add characterization coverage for `_get_files_response` query-shape and pagination behavior.
2. Extract pure file-listing query helpers inside `backend/services/file_workflow_service.py` or a
   small companion helper module if the code clearly benefits.
3. Keep SQL text, parameters, response fields, pagination math, and analysis-status fallback
   behavior unchanged.

Verification:

```powershell
uv run python -m py_compile backend/services/file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
```

Full gate after 2-3 slices:

```powershell
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git status --short
```

## Execution Log

### 2026-06-11 - P1 file listing helper extraction

Changed:

- Added characterization coverage for `_get_files_response` completed-status filtering, search
  parameter expansion, pagination shape, AI-analysis fields, and local-path status resolution.
- Extracted file-list filters, list/count query builders, row normalization, and response assembly
  from `_get_files_response` inside `backend/services/file_workflow_service.py`.

Behavior impact:

- Intended behavior change: none.
- Public route signature, response fields, SQL filter semantics, analysis-status semantics,
  pagination math, and local-path resolution behavior are preserved.
- No legacy or fallback behavior was removed.

Verification:

```powershell
uv run python -m py_compile backend\services\file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused file route helper tests passed: 29 tests.
- Full backend tests passed: 507 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P1 shared file search filter

Changed:

- Added characterization coverage for `_load_filtered_download_file_records` default status
  filtering, search parameter expansion, `LIMIT` handling, and row normalization.
- Reused `_add_file_search_condition` from `_build_file_list_filters`, so file listing and
  filtered-download record loading now share the same search-condition implementation.

Behavior impact:

- Intended behavior change: none.
- SQL search fields, LIKE parameter count, default non-completed filter behavior, max-file limit,
  and returned download record shape are preserved.
- No task execution, download behavior, route fields, legacy path, or fallback behavior changed.

Verification:

```powershell
uv run python -m py_compile backend\services\file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused file route helper tests passed: 30 tests.
- Full backend tests passed: 508 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P1 shared download record normalization

Changed:

- Added characterization coverage for `_load_download_file_records` selected-file ID de-duplication,
  original-order preservation, missing-ID reporting, SQL parameters, and blank-row fallback values.
- Extracted `_normalize_download_file_record` and reused it from both selected-file and
  filtered-download record loaders.

Behavior impact:

- Intended behavior change: none.
- Selected download ordering, missing ID reporting, fallback file names, zero defaults, filtered
  download row shape, and task execution behavior are preserved.
- No route, task status, storage schema, legacy path, or fallback behavior changed.

Verification:

```powershell
uv run python -m py_compile backend\services\file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused file route helper tests passed: 31 tests.
- Full backend tests passed: 509 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P1 file download task decision extraction

Changed:

- Added characterization coverage for `run_file_download_task` download-count mode with existing
  file records, including skip-collect behavior, downloader construction options, query parameters,
  download options, completion update, and cleanup.
- Added characterization coverage for `run_file_download_task` create-time mode with an empty file
  library, including date-range collection, download date filters, range logging, collection result
  logging, completion update, and cleanup.
- Extracted `_build_file_download_range_log`, `_collect_files_for_download`, and
  `_build_file_download_options` from `run_file_download_task`.

Behavior impact:

- Intended behavior change: none.
- Download configuration logs, existing-file skip logic, empty-library collection choice, downloader
  method calls, download option shapes, completion result shape, and cleanup behavior are preserved.
- No public API, task status semantics, storage schema, legacy path, or fallback behavior changed.

Verification:

```powershell
uv run python -m py_compile backend\services\file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused file route helper tests passed: 33 tests.
- Full backend tests passed: 511 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P1 single-file download fallback extraction

Changed:

- Added characterization coverage for `run_single_file_download_task_with_info` database-hit behavior,
  including SQL parameters, downloader payload, completed file-status update, success task update,
  and cleanup.
- Added characterization coverage for the request-info fallback when the file library misses and
  the downloader returns `skipped`.
- Added characterization coverage for the bare file-ID fallback when both the database and request
  metadata are unavailable and the downloader returns a failure value.
- Extracted `_resolve_single_download_file_info` and `_complete_single_file_download`.

Behavior impact:

- Intended behavior change: none.
- Database lookup SQL, request-info fallback, `file_{file_id}` fallback, log text, downloader payload,
  skipped/success/failure task messages, and completed local-path update behavior are preserved.
- The fallback paths remain intentionally retained and are now covered by characterization tests.
- No public API, task cancellation, schema, retry, legacy path, or config behavior changed.

Verification:

```powershell
uv run python -m py_compile backend\services\file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused file route helper tests passed: 36 tests.
- Full backend tests passed: 514 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P1 file analysis stats extraction

Changed:

- Added characterization coverage for `run_file_analysis_task` duplicate file-ID handling, mixed
  completed/cached/failed stats, per-file failure logging, and completed task update behavior.
- Added characterization coverage for the all-files-failed branch that marks the task as `failed`.
- Extracted `_analyze_group_file_with_defaults`, `_record_file_analysis_result`, and
  `_finish_file_analysis_task`.

Behavior impact:

- Intended behavior change: none.
- File-ID de-duplication, default analysis model/api options, cached-vs-completed stats, per-file
  exception handling, all-failed error semantics, task update payload shape, and log text are
  preserved.
- No public API, prompt, storage schema, task cancellation, retry, legacy path, or fallback behavior
  changed.

Verification:

```powershell
uv run python -m py_compile backend\services\file_workflow_service.py
uv run python -m unittest tests.test_file_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused file route helper tests passed: 38 tests.
- Full backend tests passed: 516 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P2 topic detail nested comments extraction

Changed:

- Added characterization coverage for `ZSXQDatabase.get_topic_detail` nested comment assembly,
  including parent/child comment placement, repliee payload shape, child comment images, and scoped
  batched image-query parameters.
- Extracted `build_topic_detail_comments` into `backend/storage/zsxq_database_helpers.py` and reused
  it from `get_topic_detail`.
- Removed the now-unused direct `topic_detail_comment_payload` import from
  `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- Comment ordering, parent-child nesting, `replied_comments` shape, image payload shape, repliee
  shape, batched image-query parameters, group scoping, and topic-detail response fields are
  preserved.
- No schema, public API, storage write path, legacy compatibility path, or fallback behavior changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused ZSXQ database helper tests passed: 15 tests.
- Full backend tests passed: 517 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P2 topic detail talk payload extraction

Changed:

- Added characterization coverage for `ZSXQDatabase.get_topic_detail` talk attachment assembly,
  including topic images, topic files, article payload, and scoped attachment-query parameters.
- Extracted `build_topic_detail_talk` into `backend/storage/zsxq_database_helpers.py`.
- Reused the helper from `get_topic_detail` while preserving the existing talk-row gate and child
  query order.

Behavior impact:

- Intended behavior change: none.
- Talk owner payload, optional `images`, optional `files`, optional `article`, attachment ordering,
  group scoping, and topic-detail response fields are preserved.
- No schema, public API, storage write path, legacy compatibility path, fallback behavior, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused ZSXQ database helper tests passed: 16 tests.
- Full backend tests passed: 518 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P2 topic detail scope extraction

Changed:

- Added characterization coverage for topic-detail scope construction with `group_id=None`,
  numeric group IDs, and empty-string group IDs.
- Extracted `topic_detail_scope` into `backend/storage/zsxq_database_helpers.py`.
- Reused the helper at the start of `ZSXQDatabase.get_topic_detail`.

Behavior impact:

- Intended behavior change: none.
- Existing scope semantics are preserved, including the compatibility detail that `group_id=None`
  leaves the base topic query unscoped while an empty string still appends `AND t.group_id = ?`.
- Base-topic SQL shape, parameter list shape, numeric group-ID casting, and child query reuse of
  `scoped_group_id` are unchanged.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused ZSXQ database helper tests passed: 17 tests.
- Full backend tests passed: 519 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P2 topic detail engagement payload extraction

Changed:

- Added characterization coverage for `ZSXQDatabase.get_topic_detail` latest-like and like-emoji
  assembly, including response shape and scoped engagement-query parameters.
- Extracted `build_topic_detail_latest_likes` and `build_topic_detail_likes_detail` into
  `backend/storage/zsxq_database_helpers.py`.
- Reused the helpers from `get_topic_detail` and removed the now-unused direct row-payload imports
  from `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- Latest-like ordering, owner payload shape, `likes_detail.emojis` shape, empty-list behavior,
  scoped query parameters, and topic-detail response fields are preserved.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused ZSXQ database helper tests passed: 18 tests.
- Full backend tests passed: 520 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P2 topic detail Q&A payload extraction

Changed:

- Added characterization coverage for `ZSXQDatabase.get_topic_detail` question/answer assembly,
  including current question owner payload shape, answer owner payload shape, and scoped Q&A query
  parameters.
- Extracted `build_topic_detail_qa` into `backend/storage/zsxq_database_helpers.py`.
- Reused the helper from the `q&a` branch of `get_topic_detail` and removed the now-unused direct
  question/answer payload imports from `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- The `q&a` type gate, query order, query parameters, optional `question` and optional `answer`
  fields, boolean coercions, and current owner payload field mapping are preserved.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Focused ZSXQ database helper tests passed: 19 tests.
- Full backend tests passed: 521 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.

### 2026-06-11 - P3 column topic detail row mapper extraction

Changed:

- Added characterization coverage for `ZSXQColumnsDatabase` topic-detail row mapping, including
  current base response shape, owner payload shape, boolean coercions, empty media/comment defaults,
  and field insertion order.
- Extracted `_topic_detail_row_to_dict` in `backend/storage/zsxq_columns_database.py`.
- Reused the helper from `get_topic_detail` while leaving SQL, scoped query parameters, media fetch
  order, comment fetch order, and return keys unchanged.

Behavior impact:

- Intended behavior change: none.
- The existing `get_topic_detail` no-row behavior, group scope semantics, owner mapping, boolean
  normalization, and lazy media/comment enrichment are preserved.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused column database helper tests passed: 9 tests.
- Full backend tests passed: 522 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P3 column topic media row mapper extraction

Changed:

- Added characterization coverage for topic file and video row mapping, including the current file
  response shape and the nested video `cover` payload shape.
- Extracted `_topic_file_row_to_dict` and `_topic_video_row_to_dict` in
  `backend/storage/zsxq_columns_database.py`.
- Reused the helpers from `get_topic_files` and `get_topic_videos` while leaving SQL, scoped query
  parameters, ordering, and return field names unchanged.

Behavior impact:

- Intended behavior change: none.
- File payload fields, video payload fields, nested cover shape, empty-list behavior, and group
  scope semantics are preserved.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused column database helper tests passed: 11 tests.
- Full backend tests passed: 524 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P3 column topic comment mapper extraction

Changed:

- Added characterization coverage for comment row mapping, including owner payload, repliee payload,
  and sticky boolean normalization.
- Added characterization coverage for comment-image row mapping, including the current nested image
  shape without a `local_path` field.
- Extracted `_topic_comment_row_to_dict` and `_comment_image_row_to_dict` in
  `backend/storage/zsxq_columns_database.py`.
- Reused the helpers from `get_topic_comments` while leaving comment SQL, per-comment image SQL,
  image query parameters, top-level vs child classification, and `replied_comments` assembly
  unchanged.

Behavior impact:

- Intended behavior change: none.
- Comment payload fields, owner/repliee shapes, sticky coercion, optional `images` field behavior,
  nested reply construction, and group scope semantics are preserved.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused column database helper tests passed: 13 tests.
- Full backend tests passed: 526 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P3 column pending media queue mapper extraction

Changed:

- Added characterization coverage for pending video download queue row mapping, pending file
  download queue row mapping, and uncached image queue row mapping.
- Extracted `_pending_video_row_to_dict`, `_pending_file_row_to_dict`, and
  `_uncached_image_row_to_dict` in `backend/storage/zsxq_columns_database.py`.
- Reused the helpers from `get_pending_videos`, `get_pending_files`, and `get_uncached_images`
  while leaving SQL branches, optional group filtering, joins, and returned field names unchanged.

Behavior impact:

- Intended behavior change: none.
- Queue payload fields, empty-list behavior, group-filtered branch behavior, unfiltered branch
  behavior, and cache/download workflow semantics are preserved.
- No schema, public API, storage write path, fallback behavior, legacy compatibility path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused column database helper tests passed: 16 tests.
- Full backend tests passed: 529 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P4 crawl source boundary helper extraction

Changed:

- Added characterization coverage for topic-source aliases: official aliases `mcp` and `cli`,
  legacy aliases `crawler` and `cookie`, and unknown source normalization.
- Added characterization coverage for `_uses_official_topic_source` under default, environment, and
  explicit request-source precedence.
- Extracted `_uses_official_topic_source` in `backend/services/crawl_service.py` and reused it at
  crawl task entrypoints instead of repeating `_resolve_topic_source(...) == "official"`.

Behavior impact:

- Intended behavior change: none.
- Request source precedence, environment fallback, default official source, legacy branch routing,
  and official branch routing are preserved.
- The old `cli` spelling remains accepted as an official-source alias and still does not shell out.
- No schema, public API, task status semantics, crawler call order, legacy behavior, fallback
  behavior, storage write path, or config semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\services\crawl_service.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused crawl route helper tests passed: 16 tests.
- Full backend tests passed: 529 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P4 legacy pagination cursor helper extraction

Changed:

- Added characterization coverage for `_offset_zsxq_end_time` timestamp formatting and
  `_topic_next_end_time` timestamp adjustment failure fallback.
- Extracted `_offset_zsxq_end_time` in `backend/crawlers/topic_pagination.py`.
- Reused the helper from `_topic_next_end_time` while leaving fetch/store loops, retry behavior,
  stop checks, one-hour skip behavior, and return fallback unchanged.

Behavior impact:

- Intended behavior change: none.
- Missing `create_time`, invalid timestamp fallback, `+0800` output format, and millisecond
  offset semantics are preserved.
- No source routing, task status, crawler call order, legacy behavior, fallback behavior, storage
  write path, or config semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\topic_pagination.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused pagination helper tests passed: 4 tests.
- Full backend tests passed: 531 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task runtime status boundary helper extraction

Changed:

- Added characterization coverage for runtime active status checks, terminal status checks, and
  legacy `stopped` normalization to `cancelled`.
- Added `ACTIVE_TASK_STATUSES`, `RUNTIME_TERMINAL_TASK_STATUSES`,
  `_is_active_task_status`, and `_is_runtime_terminal_status` in
  `backend/services/task_runtime.py`.
- Reused the helpers from ingestion-task conflict checks, task update lock release, stop handling,
  and shutdown cancellation paths.

Behavior impact:

- Intended behavior change: none.
- `pending` and `running` remain the only active runtime statuses.
- `completed`, `failed`, and `cancelled` remain the only runtime terminal statuses after
  normalization; `stopped` still normalizes to `cancelled`.
- Cancellation behavior, terminal lock release, task IDs, persisted fields, log messages, SSE
  semantics, fallback polling, and frontend task contract are preserved.
- No storage schema, task store SQL, public route response, frontend hook, legacy path, or config
  semantics changed.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Focused task runtime helper tests passed: 13 tests.
- Recommended task runtime gate passed: 32 tests, 14 PostgreSQL integration tests skipped by
  environment gate.
- Full backend tests passed: 532 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

## Stop Conditions

Pause before editing if:

- New tracked changes appear in files targeted by the current slice.
- A test failure appears outside the edited area and is not clearly pre-existing.
- The slice requires route field, schema, prompt, task status, lock, retry, or config semantic
  changes.
- The implementation grows into a broad rewrite instead of a boundary-preserving extraction.
