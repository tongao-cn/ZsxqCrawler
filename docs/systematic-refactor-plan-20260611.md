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

### 2026-06-11 - P5 task runtime ID allocation helper extraction

Changed:

- Added characterization coverage for `create_task` task ID allocation from the persisted maximum
  sequence, persisted task fields, runtime memory state, stop-flag initialization, and creation log.
- Extended the task-runtime fake store to cover the existing `create_task` store contract.
- Extracted `_allocate_task_id_locked` and reused it from `create_task` and
  `create_ingestion_task`.

Behavior impact:

- Intended behavior change: none.
- Task ID format, sequence initialization from `TaskStore.max_task_sequence()`, timestamp suffix,
  task-counter increment order, memory task fields, metadata merge, stop flag, creation log, and
  ingestion lock behavior are preserved.
- The helper intentionally keeps the original lock boundary by being called inside `_state_lock`.
- No public route response, task store SQL, SSE behavior, cancellation behavior, legacy path, or
  config semantics changed.

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

- Focused task runtime helper tests passed: 14 tests.
- Recommended task runtime gate passed: 33 tests, 14 PostgreSQL integration tests skipped by
  environment gate.
- Full backend tests passed: 533 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task runtime creation tracking helper extraction

Changed:

- Added characterization coverage for ingestion-task creation tracking: persisted stop flag,
  creation log, memory log, and memory stop flag.
- Tightened the ingestion-task helper test cleanup so runtime memory logs are removed after the
  test.
- Extracted `_initialize_task_tracking_locked` and `_persist_task_creation_tracking`, then reused
  them from `create_task` and `create_ingestion_task`.

Behavior impact:

- Intended behavior change: none.
- Runtime memory log initialization, memory stop-flag initialization, persisted stop-flag reset,
  creation log text, task ID allocation, task creation order, and ingestion lock behavior are
  preserved.
- The ingestion task memory initialization remains inside the same `_state_lock` block as
  `current_tasks` assignment.
- No public route response, task store SQL, SSE behavior, cancellation behavior, legacy path, or
  config semantics changed.

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

- Focused task runtime helper tests passed: 14 tests.
- Recommended task runtime gate passed: 33 tests, 14 PostgreSQL integration tests skipped by
  environment gate.
- Full backend tests passed: 533 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P6 task API type surface split

Changed:

- Added `frontend/src/lib/api/taskTypes.ts` for task-related frontend API types:
  `Task`, `TaskCreateResponse`, and `ApiErrorDetail`.
- Kept `frontend/src/lib/api/types.ts` as the compatibility facade by re-exporting those task
  types.
- Updated internal API clients to import task-specific types from `taskTypes.ts` while keeping
  existing external imports from `@/lib/api` valid.

Behavior impact:

- Intended behavior change: none.
- Public frontend import path `@/lib/api`, exported type names, task status union, task response
  shape, task conflict detail shape, API client inheritance, request URLs, request bodies, and
  runtime behavior are preserved.
- No backend route, storage schema, SSE behavior, fallback polling, legacy path, or config
  semantics changed.

Verification:

```powershell
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P6 file API type surface split

Changed:

- Added `frontend/src/lib/api/fileTypes.ts` for file-workbench frontend API types:
  `FileItem`, `FileAIAnalysis`, and `FileStatus`.
- Kept `frontend/src/lib/api/types.ts` as the compatibility facade by re-exporting those file
  types.
- Updated `frontend/src/lib/api/files.ts` to import file-specific types from `fileTypes.ts` while
  leaving generic `PaginatedResponse<T>` in `types.ts`.

Behavior impact:

- Intended behavior change: none.
- Public frontend import path `@/lib/api`, exported type names, file list item shape, file AI
  analysis shape, file status shape, request URLs, request bodies, and runtime behavior are
  preserved.
- `PaginatedResponse<T>` remains in the shared type facade because it is used by both file and
  topic/group clients.
- No backend route, storage schema, task behavior, SSE behavior, fallback polling, legacy path, or
  config semantics changed.

Verification:

```powershell
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P6 column API type surface split

Changed:

- Added `frontend/src/lib/api/columnTypes.ts` for column-workbench frontend API types:
  `ColumnInfo`, `ColumnTopic`, `ColumnTopicDetail`, `ColumnImage`, `ColumnVideo`, `ColumnFile`,
  `ColumnComment`, `ColumnsStats`, and `ColumnsFetchSettings`.
- Kept `frontend/src/lib/api/types.ts` as the compatibility facade by re-exporting those column
  types.
- Updated `frontend/src/lib/api/columns.ts` to import column-specific types from `columnTypes.ts`.

Behavior impact:

- Intended behavior change: none.
- Public frontend import path `@/lib/api`, exported type names, column list/detail/comment/media
  shapes, column fetch settings shape, request URLs, request bodies, and runtime behavior are
  preserved.
- No backend route, storage schema, task behavior, SSE behavior, fallback polling, legacy path, or
  config semantics changed.

Verification:

```powershell
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P6 group API type surface split

Changed:

- Added `frontend/src/lib/api/groupTypes.ts` for group/topic/account frontend API types:
  `Topic`, `TopicOwner`, `TopicDetail`, `FetchMoreCommentsResponse`, `Group`, `GroupStats`,
  `Account`, and `AccountSelf`.
- Kept `frontend/src/lib/api/types.ts` as the compatibility facade by re-exporting those
  group/topic/account types.
- Updated `frontend/src/lib/api/groups.ts` to import group-specific types from `groupTypes.ts`
  while leaving shared `PaginatedResponse<T>` in `types.ts`.

Behavior impact:

- Intended behavior change: none.
- Public frontend import path `@/lib/api`, exported type names, group/topic/account response
  shapes, pagination shape, request URLs, request bodies, and runtime behavior are preserved.
- `PaginatedResponse<T>` remains in the shared type facade because both file and group clients use
  it.
- No backend route, storage schema, task behavior, SSE behavior, fallback polling, legacy path, or
  config semantics changed.

Verification:

```powershell
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P6 core API type surface split

Changed:

- Added `frontend/src/lib/api/coreTypes.ts` for the core `DatabaseStats` frontend API type.
- Kept `frontend/src/lib/api/types.ts` as the compatibility facade by re-exporting
  `DatabaseStats`.
- Updated `frontend/src/lib/api/core.ts` to import `DatabaseStats` from `coreTypes.ts`.

Behavior impact:

- Intended behavior change: none.
- Public frontend import path `@/lib/api`, exported `DatabaseStats` name, database stats response
  shape, request URL, and runtime behavior are preserved.
- No backend route, storage schema, task behavior, SSE behavior, fallback polling, legacy path, or
  config semantics changed.

Verification:

```powershell
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P6 analysis API type surface split

Changed:

- Added `frontend/src/lib/api/analysisTypes.ts` for daily analysis, stock-topic analysis, stock
  question, and A-share analysis frontend API types.
- Kept `frontend/src/lib/api/types.ts` as the compatibility facade by re-exporting those analysis
  types.
- Updated `frontend/src/lib/api/analysis.ts` to import analysis-specific types from
  `analysisTypes.ts`.
- Left `ApiResponse<T>` and shared `PaginatedResponse<T>` in `types.ts`.

Behavior impact:

- Intended behavior change: none.
- Public frontend import path `@/lib/api`, exported type names, daily report shape, stock-topic
  analysis shapes, A-share status/chart/export shapes, request URLs, request bodies, and runtime
  behavior are preserved.
- No backend route, storage schema, task behavior, SSE behavior, fallback polling, legacy path,
  prompt, AI output, or config semantics changed.

Verification:

```powershell
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P7 unused frontend runtime dependency removal

Changed:

- Removed the unused direct frontend dependency `@babel/runtime` from `frontend/package.json` and
  `frontend/package-lock.json`.
- Kept unrelated optional Next.js SWC lockfile entries unchanged after npm initially produced
  lockfile noise.
- Left `tailwind.config.js` and `tw-animate-css` untouched because the Tailwind animation setup
  needs separate config-semantics review.

Behavior impact:

- Intended behavior change: none.
- Frontend source and configuration scans found no `@babel/runtime` imports or config references
  before removal.
- `npm --prefix frontend ls @babel/runtime` now reports the package as absent.
- No frontend source code, route behavior, backend route, storage schema, task behavior, fallback
  polling, legacy path, prompt, AI output, or config semantics changed.

Verification:

```powershell
rg -n "@babel/runtime" frontend\package.json frontend\package-lock.json frontend\src frontend -g "*.json" -g "*.ts" -g "*.tsx" -g "*.js" -g "*.mjs"
npm --prefix frontend ls @babel/runtime
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `@babel/runtime` has no remaining source, config, package, or lockfile references.
- `npm --prefix frontend ls @babel/runtime` reports `(empty)`.
- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P7 unused Python data dependency removal

Changed:

- Removed the unused direct Python dependency `pandas` from `pyproject.toml`.
- Updated `uv.lock`, which also removed `pandas`-only transitive lock entries:
  `python-dateutil`, `pytz`, `six`, and `tzdata`.
- Left `tomli`, `faster-whisper`, and other direct dependencies in place because current source
  paths still use them or require them as compatibility/feature dependencies.

Behavior impact:

- Intended behavior change: none.
- Source, script, test, README, and docs scans found no `pandas`, `pd.`, `DataFrame`, or related
  transitive package usage before removal.
- No backend route, storage schema, task behavior, fallback path, legacy path, AI output, or config
  semantics changed.

Verification:

```powershell
rg -n "pandas|pd\.|DataFrame|python-dateutil|dateutil|pytz|tzdata|\bsix\b" backend scripts tests README.md docs pyproject.toml uv.lock -g "*.py" -g "*.md" -g "*.toml" -g "*.lock"
uv lock --check
uv tree | rg "pandas|python-dateutil|pytz|tzdata|\bsix\b"
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- No source, script, test, README, docs, project, or lock references remain for `pandas` or the
  removed pandas-only transitive packages.
- `uv lock --check` passed.
- `uv tree` has no remaining `pandas`, `python-dateutil`, `pytz`, `six`, or `tzdata` entries.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P8 README runtime command alignment

Changed:

- Updated README frontend startup guidance to use the repository-standard root command:
  `npm --prefix frontend run dev`.
- Corrected the documented default frontend API target from `http://localhost:8208` to
  `http://localhost:8508`, matching `frontend/src/lib/api/client.ts`, `frontend/next.config.ts`,
  and `backend/main.py`.

Behavior impact:

- Intended behavior change: none.
- This is a documentation-only slice. No runtime code, route behavior, storage schema, task
  behavior, fallback path, legacy path, AI output, dependency declaration, or config semantics
  changed.

Verification:

```powershell
rg -n "8208|8508|npm run dev|cd frontend|npm --prefix frontend" README.md frontend\package.json frontend\next.config.ts frontend\src\lib\api\client.ts backend\main.py
npm --prefix frontend run build
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- README now documents `8508`, matching backend default port and frontend API defaults.
- README no longer documents a root-to-frontend `cd frontend` startup sequence.
- Frontend build passed.
- Full backend tests passed: 533 tests, 15 skipped.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task shutdown resource-stop helper extraction

Changed:

- Extracted `_request_stop_for_resources()` from `request_runtime_shutdown()` to isolate
  registered crawler/downloader stop notification.
- Added characterization coverage that resources without `set_stop_flag` are ignored while
  stoppable resources still receive the stop request.

Behavior impact:

- Intended behavior change: none.
- Shutdown still marks active tasks stopped, notifies registered crawlers/downloaders, cancels
  active tasks, releases task locks through `update_task()`, clears SSE connections, stops lock
  heartbeats, and clears runtime task thread tracking.
- No public route response, task store SQL, SSE behavior, cancellation semantics, fallback polling,
  legacy path, config semantics, or frontend hook behavior changed.

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

- Focused task runtime tests passed: 15 tests.
- Recommended task runtime gate passed: 34 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 534 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 stop-task resource fallback helper extraction

Changed:

- Added characterization coverage for `stop_task()` using the global
  `crawler_runtime.crawler_instance` fallback when no task-specific crawler is registered.
- Extracted `_request_stop_for_task_resources()` from `stop_task()` to isolate task-specific
  crawler/downloader stop notification plus the retained global crawler fallback.

Behavior impact:

- Intended behavior change: none.
- `stop_task()` still returns `False` for missing or non-active tasks; for active tasks it still
  sets the in-memory and persisted stop flags, logs the stop request, notifies the same crawler or
  downloader resource path, updates the task to `cancelled`, and releases the task lock through
  `update_task()`.
- The global crawler fallback remains intentionally preserved and is now covered by a
  characterization test.
- No public route response, task store SQL, task status normalization, SSE behavior, fallback
  polling, storage schema, legacy path, config semantics, or frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 16 tests.
- Recommended task runtime gate passed: 35 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 535 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 terminal lock release helper extraction

Changed:

- Added characterization coverage for `update_task()` logging the existing
  `⚠️ 释放任务锁失败: ...` message when `release_task_lock()` raises.
- Extracted `_release_task_lock_on_terminal_status()` from `update_task()` to isolate terminal
  lock release and its existing failure-log behavior.

Behavior impact:

- Intended behavior change: none.
- `update_task()` still normalizes `stopped` to `cancelled`, refuses to overwrite an already
  cancelled task with a non-cancelled status, updates memory and persistent state, writes the same
  status-update log, releases task locks only for runtime terminal statuses, and logs the same
  lock-release failure message when release fails.
- No public route response, task store SQL, task status normalization, task cancellation behavior,
  SSE behavior, fallback polling, storage schema, legacy path, config semantics, or frontend hook
  behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 17 tests.
- Recommended task runtime gate passed: 36 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 536 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 cleanup runtime tracking helper extraction

Changed:

- Added characterization coverage for `cleanup_tasks()` normalizing negative `keep_latest` to `0`
  and forgetting only runtime tracking for tasks removed by the persistent store cleanup.
- Extracted `_forget_task_tracking_locked()` to centralize cleanup of `current_tasks`,
  `task_logs`, `task_stop_flags`, and `sse_connections` for removed task IDs.

Behavior impact:

- Intended behavior change: none.
- `cleanup_tasks()` still calls the persistent store cleanup first, derives remaining IDs from the
  store after cleanup, and only removes runtime tracking for task IDs no longer present.
- The persistent cleanup result shape, `keep_latest` normalization, task store SQL behavior,
  cancellation behavior, SSE behavior, fallback polling, storage schema, legacy path, config
  semantics, and frontend hook behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 18 tests.
- Recommended task runtime gate passed: 37 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 537 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 pending task state builder extraction

Changed:

- Added characterization coverage for `create_ingestion_task()` when the task store returns no
  task object and no conflict, preserving the in-memory pending-task fallback shape.
- Extracted `_build_pending_task_state()` and reused it for ordinary task creation and the
  ingestion-task fallback path.

Behavior impact:

- Intended behavior change: none.
- Ordinary task creation still allocates the same task ID, writes the same pending memory fields,
  passes the same metadata to the persistent store, initializes stop flags/logs in the same order,
  and emits the same creation log text.
- Ingestion task creation still preserves store-returned task objects when present and only builds
  the fallback pending memory task when the store returns no task and no existing conflict.
- No public route response, task store SQL, ingestion lock behavior, task ID allocation,
  cancellation behavior, SSE behavior, fallback polling, storage schema, legacy path, config
  semantics, or frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 19 tests.
- Recommended task runtime gate passed: 38 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 538 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task log subscriber snapshot helper extraction

Changed:

- Added characterization coverage for `broadcast_log()` ignoring a failing task-log subscriber while
  still delivering the log message to the remaining subscribers.
- Extracted `_task_log_subscribers_snapshot_locked()` to isolate the locked snapshot of
  `sse_connections` before broadcasting.

Behavior impact:

- Intended behavior change: none.
- `broadcast_log()` still takes a snapshot under `_state_lock`, delivers the same log message to
  each subscriber with `put_nowait()`, and preserves the existing behavior of ignoring subscriber
  exceptions so one failed SSE/log queue does not block the rest.
- No public route response, task store SQL, task status behavior, task cancellation behavior, task
  log text, SSE framing, fallback polling, storage schema, legacy path, config semantics, or
  frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 20 tests.
- Recommended task runtime gate passed: 39 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 539 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task log append helper extraction

Changed:

- Added characterization coverage for `add_task_log()` using the persisted log text returned by
  `TaskStore.add_log()` for both in-memory task logs and broadcasts.
- Extracted `_append_task_log_locked()` to centralize the locked in-memory task-log list creation
  and append behavior.

Behavior impact:

- Intended behavior change: none.
- `add_task_log()` still persists the input log message first, stores the persisted/formatted log
  text in `task_logs`, and broadcasts that same persisted/formatted log text afterward.
- The in-memory fallback for tasks without an existing `task_logs` entry is preserved.
- No public route response, task store SQL, task status behavior, task cancellation behavior, task
  log text source, SSE framing, fallback polling, storage schema, legacy path, config semantics, or
  frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 21 tests.
- Recommended task runtime gate passed: 40 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 540 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 runtime shutdown snapshot helper extraction

Changed:

- Added characterization coverage for `request_runtime_shutdown()` marking in-memory stop flags
  before stopping registered runtime resources.
- Added characterization coverage for shutdown stopping task-lock heartbeat events and clearing
  runtime task thread tracking.
- Extracted `_prepare_runtime_shutdown_snapshot_locked()` to isolate locked task/resource snapshot
  collection and stop-flag marking.
- Extracted `_clear_runtime_shutdown_tracking_locked()` to centralize shutdown cleanup of crawler,
  downloader, SSE, and heartbeat tracking state.

Behavior impact:

- Intended behavior change: none.
- `request_runtime_shutdown()` still marks active task stop flags while holding `_state_lock`,
  stops registered crawler/downloader resources from snapshots, persists stop flags only for active
  tasks, updates active tasks to `cancelled`, clears runtime resource/SSE tracking, stops heartbeat
  events, and clears runtime task thread tracking in the same order.
- No public route response, task store SQL, task status field, cancellation message, lock release
  behavior, SSE framing, fallback polling, storage schema, legacy path, config semantics, or
  frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization test passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 23 tests.
- Recommended task runtime gate passed: 42 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 542 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task stop flag reader helper extraction

Changed:

- Added characterization coverage for `is_task_stopped()` short-circuiting when the in-memory stop
  flag is already set.
- Added characterization coverage for `is_task_stopped()` falling back to the persisted task-store
  stop flag when no in-memory stop flag is set.
- Extracted `_task_stop_flag_locked()` to isolate the locked in-memory stop-flag read from
  `task_stop_flags`.

Behavior impact:

- Intended behavior change: none.
- `is_task_stopped()` still reads the in-memory stop flag under `_state_lock` and preserves the
  existing short-circuit behavior before consulting `TaskStore.is_stopped()`.
- No public route response, task store SQL, task status field, cancellation behavior, stop-flag
  persistence, fallback polling, storage schema, legacy path, config semantics, or frontend hook
  behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 25 tests.
- Recommended task runtime gate passed: 44 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 544 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task stop resource snapshot helper extraction

Changed:

- Added characterization coverage for `stop_task()` stopping the registered file downloader along
  with the registered crawler.
- Added characterization coverage for `stop_task()` marking the in-memory stop flag before
  stopping registered runtime resources.
- Extracted `_prepare_task_stop_resources_locked()` to isolate the locked `task_stop_flags`,
  `crawler_instances`, and `file_downloader_instances` access used by `stop_task()`.

Behavior impact:

- Intended behavior change: none.
- `stop_task()` still returns `False` for missing or inactive tasks, marks the in-memory stop flag
  under `_state_lock`, persists the stop flag, appends the existing stop log message, stops the
  registered crawler or global crawler fallback, stops the registered downloader, updates the task
  to `cancelled`, and preserves lock release behavior through `update_task()`.
- No public route response, task store SQL, task status field, cancellation message, stop-flag
  persistence, crawler fallback behavior, downloader stop behavior, fallback polling, storage
  schema, legacy path, config semantics, or frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 26 tests.
- Recommended task runtime gate passed: 45 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 545 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task log fallback helper extraction

Changed:

- Added characterization coverage for `get_task_logs_state()` preferring persisted task logs over
  in-memory task logs when persisted logs are available.
- Added characterization coverage for `get_task_logs_state()` returning `None` for unknown tasks
  that have no in-memory log fallback.
- Extracted `_has_task_logs_locked()` and `_task_logs_copy_locked()` to isolate locked in-memory
  `task_logs` existence and copy reads.

Behavior impact:

- Intended behavior change: none.
- `get_task_logs_state()` still resolves task state first, returns `None` for unknown tasks without
  memory logs before reading persisted logs, preserves persisted-log priority, and returns a copied
  in-memory log list as the fallback.
- No public route response, task store SQL, task status behavior, task log text, SSE framing,
  fallback polling, storage schema, legacy path, config semantics, or frontend hook behavior
  changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 28 tests.
- Recommended task runtime gate passed: 47 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 547 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task state fallback helper extraction

Changed:

- Added characterization coverage for `get_task_state()` preferring persisted task state over
  the in-memory runtime fallback when both exist.
- Added characterization coverage for `get_task_state()` using the in-memory runtime fallback
  and preserving status normalization from `stopped` to `cancelled`.
- Extracted `_memory_task_state_locked()` to isolate locked `current_tasks` fallback reads.

Behavior impact:

- Intended behavior change: none.
- `get_task_state()` still reads persisted task state first, only falls back to `current_tasks`
  when no persisted task exists, and still normalizes the returned status through
  `_normalize_task()`.
- No public route response, task store SQL, task status field, cancellation behavior, task log
  fallback, SSE framing, fallback polling, storage schema, legacy path, config semantics, or
  frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 30 tests.
- Recommended task runtime gate passed: 49 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 549 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 update-task memory helper extraction

Changed:

- Added characterization coverage for `update_task()` updating in-memory task state when a
  matching runtime task is present.
- Added characterization coverage for `update_task()` returning without store writes or task logs
  when the task is unknown to both persisted and in-memory state.
- Extracted `_has_memory_task_locked()` and `_update_memory_task_locked()` to isolate locked
  `current_tasks` existence checks and updates.

Behavior impact:

- Intended behavior change: none.
- `update_task()` still normalizes incoming status first, returns early for unknown tasks,
  preserves the cancelled-status overwrite guard, updates in-memory state before persisted state
  when present, appends the existing status-update log text, and releases task locks only for
  terminal statuses.
- No public route response, task store SQL, task status field, cancellation behavior, task log
  text, SSE framing, fallback polling, storage schema, legacy path, config semantics, or frontend
  hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 32 tests.
- Recommended task runtime gate passed: 51 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 551 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task log subscription helper extraction

Changed:

- Added characterization coverage for `unsubscribe_task_logs()` ignoring an unknown subscriber
  while preserving existing subscribers.
- Added characterization coverage for `unsubscribe_task_logs()` being a no-op for unknown task
  IDs.
- Extracted `_add_task_log_subscriber_locked()` and `_remove_task_log_subscriber_locked()` to
  isolate locked `sse_connections` subscription mutations.

Behavior impact:

- Intended behavior change: none.
- `subscribe_task_logs()` still returns a new queue and appends it to the same per-task subscriber
  list.
- `unsubscribe_task_logs()` still ignores missing task IDs and unknown subscriber queues, removes
  only the requested queue, and deletes the task entry when the last subscriber is removed.
- No public route response, SSE frame format, queue type, broadcast order, failing-subscriber
  handling, task log text, fallback polling, storage schema, legacy path, config semantics, or
  frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 34 tests.
- Recommended task runtime gate passed: 53 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 553 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 runtime task thread helper extraction

Changed:

- Added characterization coverage for `enqueue_runtime_task()` preserving the existing runtime
  thread name format.
- Extracted `_register_runtime_task_thread_locked()` and `_forget_runtime_task_thread_locked()` to
  isolate locked `runtime_task_threads` registration and cleanup.

Behavior impact:

- Intended behavior change: none.
- `enqueue_runtime_task()` still creates daemon threads named `zsxq-task-{task_id}`, registers the
  thread before starting it, starts task lock heartbeat before invoking the task function, awaits
  coroutine task functions, stops task lock heartbeat in `finally`, and removes runtime thread
  tracking after task completion.
- No public route response, task status field, cancellation behavior, heartbeat behavior, thread
  name, daemon flag, fallback polling, storage schema, legacy path, config semantics, or frontend
  hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 34 tests.
- Recommended task runtime gate passed: 53 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 553 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task lock heartbeat helper extraction

Changed:

- Added characterization coverage for `_start_task_lock_heartbeat()` skipping non-ingestion tasks
  without starting a heartbeat thread.
- Added characterization coverage for `_start_task_lock_heartbeat()` registering ingestion task
  heartbeat stop events and `_stop_task_lock_heartbeat()` clearing and setting them.
- Extracted `_register_task_lock_heartbeat_locked()`, `_pop_task_lock_heartbeat_locked()`, and
  `_task_lock_heartbeat_ids_locked()` to isolate locked `runtime_task_heartbeats` mutations and
  snapshots.

Behavior impact:

- Intended behavior change: none.
- Task lock heartbeat still only starts for tasks with `ingestion_lock_key == "ingestion"`, still
  creates daemon threads named `zsxq-lock-heartbeat-{task_id}`, still swallows heartbeat store
  errors, and still sets the stop event when stopped or during runtime shutdown.
- No public route response, task status field, cancellation behavior, heartbeat interval, lock
  lease minutes, fallback polling, storage schema, legacy path, config semantics, or frontend hook
  behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Characterization tests passed on the pre-refactor code before the helper extraction.
- Focused task runtime tests passed: 36 tests.
- Recommended task runtime gate passed: 55 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 555 tests, 15 skipped.
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
