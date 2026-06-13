# Systematic Refactor Plan - 2026-06-11

## Purpose

Coordinate safe refactor, cleanup, and governance work for ZsxqCrawler without changing business
logic, public APIs, response shapes, config semantics, task behavior, SQL side effects, prompts, or
fallback compatibility.

This is the active plan for the next work rounds. Keep each implementation slice small, verified,
and committed independently.

## Baseline

Observed on 2026-06-11:

- Earlier `git status --short` showed root `tmp_stock_analysis_*` scratch files; tracked scratch
  artifacts were later cleaned in the P0 slice, while untracked scratch files remain preserved and
  ignored.
- `uv run python -m unittest discover -s tests`: 506 tests passed, 15 skipped.
- `npm --prefix frontend run build`: passed.
- `uv run python scripts\scan_postgres_compat_debt.py`: no SQLite compatibility patterns found.
- The previous `docs/module-refactor-execution-plan-20260610.md` is a completed plan and should
  remain as historical evidence, not the active execution plan.

## Guardrails

- Work directly on `main`.
- Stage and commit only files touched for the current slice.
- Do not modify remaining untracked root `tmp_stock_analysis_*` files unless cleanup is explicitly
  requested.
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
| P0 | Root `tmp_stock_analysis_*` files | Remove tracked scratch artifacts and ignore future root scratch | Low | `git status --short`; `git check-ignore`; reference search | No | Preserve remaining untracked files |
| P1 | `backend/services/file_workflow_service.py` | Extract file listing filters, pagination, row mapping, and status helpers | Medium | `py_compile`; `tests.test_file_routes_helpers` | Yes | Preserve task status, response fields, error messages, paths, and side effects |
| P2 | `backend/storage/zsxq_database.py` | Extract topic/detail row mappers and payload builders | Medium | `tests.test_zsxq_database_helpers`; PG smoke only if SQL changes | Yes | Do not change schema, `db_compat.py`, runtime DDL, or compat method names |
| P3 | `backend/storage/zsxq_columns_database.py` | Extract column topic/comment row mappers | Medium | `tests.test_zsxq_columns_database_helpers`; column service tests | Yes | Preserve commit order and return shapes |
| P4 | `backend/crawlers/topic_pagination.py`, `backend/services/crawl_service.py` | Clarify pagination and official-vs-legacy source boundaries | Medium-high | Crawl route tests; official topic tests | Yes | Isolate legacy path before considering removal |
| P5 | `backend/services/task_runtime.py`, `backend/storage/task_store.py`, `frontend/src/hooks/useTaskStatus.ts` | Reduce global task-runtime state and align frontend polling/SSE behavior | High | Task tests; frontend build; manual task smoke if UI changes | Yes | Preserve cancellation, terminal ordering, lock release, and fallback polling |
| P6 | `frontend/src/lib/api/types.ts`, `frontend/src/lib/api/*` | Split API type surface by domain while keeping compatibility facade | Medium | `npm --prefix frontend run build` | Maybe | Keep `frontend/src/lib/api.ts` exports |
| P7 | `frontend/package.json`, `pyproject.toml` | Audit suspicious direct dependencies in isolated slices | Low-medium | `npm ls`; frontend build; lock diff review | No | Do not mix dependency cleanup with behavior refactors |
| P8 | `README.md`, `docs/project-architecture-roadmap.md` | Keep docs aligned with final module boundaries and verification commands | Low | grep references; relevant tests/builds | No | Archive stale plans only when cleanup is in scope |
| P9 | `backend/crawlers/zsxq_file_downloader.py` | Extract tested download filename, retry, and file-body helpers from the large crawler class | Medium | `py_compile`; `tests.test_zsxq_file_downloader_helpers`; full backend tests | Yes | Preserve signed URL, retry, stop, partial-file cleanup, and status-update behavior |

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

### 2026-06-11 - P5 runtime resource helper extraction

Changed:

- Added characterization coverage for `unregister_task_crawler()` removing registered crawlers and
  remaining idempotent for unknown task IDs.
- Extracted `_register_task_crawler_locked()`, `_unregister_task_crawler_locked()`,
  `_task_crawler_locked()`, `_task_file_downloader_locked()`,
  `_runtime_crawlers_snapshot_locked()`, `_runtime_file_downloaders_snapshot_locked()`, and
  `_clear_runtime_resource_tracking_locked()` to isolate locked crawler/downloader runtime resource
  mutations and snapshots.

Behavior impact:

- Intended behavior change: none.
- `register_task_crawler()` and `unregister_task_crawler()` still mutate the same runtime crawler
  tracking under `_state_lock`.
- `stop_task()` still marks the memory stop flag before stopping resources, still stops registered
  crawlers/downloaders first, and still falls back to the global crawler when no task crawler is
  registered.
- Runtime shutdown still snapshots crawler/downloader resources before stopping them and clears the
  same resource tracking dictionaries.
- No public route response, task status field, cancellation behavior, stop-resource ordering,
  global crawler fallback, fallback polling, storage schema, legacy path, config semantics, or
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
- Focused task runtime tests passed: 37 tests.
- Recommended task runtime gate passed: 56 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 556 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 runtime thread clear helper extraction

Changed:

- Extracted `_clear_runtime_task_threads_locked()` so runtime task thread registration, removal, and
  shutdown clearing now go through the same locked helper boundary.
- Reused the existing characterization coverage for `request_runtime_shutdown()` clearing
  `runtime_task_threads` after stopping runtime heartbeats.

Behavior impact:

- Intended behavior change: none.
- Runtime shutdown still clears `runtime_task_threads` under `_state_lock` after heartbeat stop
  requests are issued.
- No public route response, task status field, cancellation behavior, stop-resource ordering,
  heartbeat semantics, fallback polling, storage schema, legacy path, config semantics, or frontend
  hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_request_runtime_shutdown_stops_heartbeats_and_clears_runtime_threads -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Existing characterization test passed before the helper extraction: 1 test.
- Post-refactor characterization test passed: 1 test.
- Focused task runtime tests passed: 37 tests.
- Recommended task runtime gate passed: 56 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 556 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 task stop flag helper extraction

Changed:

- Extracted `_set_task_stop_flag_locked()` so task creation, user stop, and runtime shutdown stop
  flag mutations go through a single locked helper boundary.
- Reused existing characterization coverage for initial stop flag state, user stop ordering,
  runtime shutdown ordering, and `is_task_stopped()` memory short-circuit behavior.

Behavior impact:

- Intended behavior change: none.
- Task creation still initializes the in-memory stop flag to `False`.
- `stop_task()` still marks the in-memory stop flag before stopping registered resources and before
  updating the persisted task status.
- Runtime shutdown still marks active in-memory tasks as stopped before resource stop requests.
- No public route response, task status field, cancellation behavior, stop-resource ordering,
  global crawler fallback, fallback polling, storage schema, legacy path, config semantics, or
  frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_create_task_uses_persisted_sequence_and_initializes_runtime_state tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_create_ingestion_task_builds_memory_task_when_store_returns_no_task tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_stop_task_marks_memory_stop_flag_before_stopping_resources tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_request_runtime_shutdown_marks_stop_flags_before_stopping_resources tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_is_task_stopped_short_circuits_when_memory_flag_is_set -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Existing characterization tests passed before the helper extraction: 5 tests.
- Post-refactor characterization tests passed: 5 tests.
- Focused task runtime tests passed: 37 tests.
- Recommended task runtime gate passed: 56 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 556 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 memory task helper extraction

Changed:

- Extracted `_set_memory_task_locked()` for in-memory task writes during regular task creation and
  ingestion task creation.
- Extracted `_memory_tasks_snapshot_locked()` for runtime shutdown task snapshotting.
- Reused existing characterization coverage for memory task shape, ingestion fallback memory task
  creation, runtime shutdown cancellation, and runtime shutdown stop-flag ordering.

Behavior impact:

- Intended behavior change: none.
- `create_task()` still builds the same pending in-memory task before persisting it.
- `create_ingestion_task()` still stores the task returned by `create_task_with_lock()`, or builds
  the same pending fallback task when the store returns no task.
- Runtime shutdown still snapshots `current_tasks` under `_state_lock` before stopping resources or
  updating task statuses.
- No public route response, task status field, cancellation behavior, shutdown snapshot ordering,
  fallback polling, storage schema, legacy path, config semantics, or frontend hook behavior
  changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_create_task_uses_persisted_sequence_and_initializes_runtime_state tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_create_ingestion_task_allows_different_group_when_no_conflict tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_create_ingestion_task_builds_memory_task_when_store_returns_no_task tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_request_runtime_shutdown_cancels_running_resources tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_request_runtime_shutdown_marks_stop_flags_before_stopping_resources -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Existing characterization tests passed before the helper extraction: 5 tests.
- Post-refactor characterization tests passed: 5 tests.
- Focused task runtime tests passed: 37 tests.
- Recommended task runtime gate passed: 56 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 556 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P5 latest task query helper extraction

Changed:

- Added characterization coverage for `get_latest_task_by_type()` filtering by task type, status,
  normalized group ID, and newest `created_at`.
- Locked the legacy `stopped` to `cancelled` read compatibility behavior for latest-task queries.
- Extracted `_matches_latest_task_query()` and `_task_created_at_sort_value()` so latest-task
  filtering and sorting are named, focused helpers.

Behavior impact:

- Intended behavior change: none.
- `get_latest_task_by_type()` still reads through `list_tasks()`, so persisted task normalization
  and legacy `stopped` status compatibility are preserved.
- Status filtering, task type filtering, group ID normalization, missing `created_at` fallback to
  `datetime.min`, and newest-first selection are unchanged.
- No public route response, task status field, cancellation behavior, fallback polling, storage
  schema, legacy path, config semantics, or frontend hook behavior changed.

Verification:

```powershell
uv run python -m unittest tests.test_task_runtime_helpers.TaskRuntimeHelperTests.test_get_latest_task_by_type_filters_status_group_and_sorts_latest -v
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- New characterization test passed on the pre-refactor code before helper extraction: 1 test.
- Post-refactor characterization test passed: 1 test.
- Focused task runtime tests passed: 38 tests.
- Recommended task runtime gate passed: 57 tests, 14 PostgreSQL integration tests skipped by
  configuration.
- Full backend tests passed: 557 tests, 15 skipped.
- Frontend build passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Git diff whitespace check passed.

### 2026-06-11 - P0 root stock-analysis scratch cleanup

Changed:

- Removed tracked root scratch artifacts `tmp_stock_analysis_missing_45.json`,
  `tmp_stock_analysis_remaining_35.json`, and
  `tmp_stock_analysis_remaining_35_concurrency5.json`.
- Added root `.gitignore` coverage for `/tmp_stock_analysis_*` so future stock-analysis scratch
  scripts, logs, and result files do not pollute `git status`.
- Preserved the existing untracked root `tmp_stock_analysis_*` files; they were not moved, edited,
  or deleted.

Evidence:

- Before documenting this cleanup slice, `rg` found no references to the removed tracked filenames
  or their `missing_45`/`remaining_35` suffixes outside the files themselves.
- The two tracked `remaining_35` files had identical content.
- `git log --oneline -- tmp_stock_analysis_missing_45.json
  tmp_stock_analysis_remaining_35.json tmp_stock_analysis_remaining_35_concurrency5.json` showed
  they entered the repository as one-off workspace/result artifacts.

Behavior impact:

- Intended behavior change: none.
- No runtime code, public route response, task status field, storage schema, fallback path, config
  semantics, dependency, or frontend behavior changed.
- Remaining scratch files stay on disk but are ignored by Git unless explicitly force-added.

Verification:

```powershell
git status --short
git check-ignore -v tmp_stock_analysis_run_pending_21_40_20260611_concurrency5.py tmp_stock_analysis_run_pending_21_40_20260611_concurrency5_20260611_162420_result.json tmp_stock_analysis_run_2_concurrency2_result.json
rg -n "tmp_stock_analysis_missing_45|tmp_stock_analysis_remaining_35|missing_45|remaining_35" . --glob '!frontend/.next/**' --glob '!node_modules/**' --glob '!output/**' --glob '!docs/systematic-refactor-plan-20260611.md'
git diff --check
```

Result:

- `git status --short` shows only the intended tracked cleanup files for this slice.
- `git check-ignore -v` confirms `/tmp_stock_analysis_*` covers representative root scratch
  scripts and JSON result files.
- Reference search, excluding this execution log, found no matches for the removed tracked scratch
  artifact names.
- Git diff whitespace check passed.

### 2026-06-11 - P5 pending memory task helper extraction

Changed:

- Extracted `_set_pending_memory_task_locked` in `backend/services/task_runtime.py`.
- Reused it from `create_task` and `create_ingestion_task` to keep pending in-memory task
  construction in one place.

Behavior impact:

- Intended behavior change: none.
- Public task APIs, task IDs, status values, result fields, metadata, ingestion lock behavior,
  fallback memory task behavior, log messages, stop flags, and persistence calls remain unchanged.
- Creation ordering is intentionally preserved:
  - `create_task` still allocates and records the memory pending task before `store.create_task`,
    then initializes logs and stop flag after persistence.
  - `create_ingestion_task` still writes memory state only after `create_task_with_lock` succeeds,
    and still returns the normalized existing task without mutating memory when a lock conflict is
    found.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.

### 2026-06-11 - P5 runtime task runner helper extraction

Changed:

- Extracted `_run_runtime_task` from the nested runner inside `enqueue_runtime_task`.
- Kept `enqueue_runtime_task` responsible for thread construction, runtime thread registration, and
  starting the daemon thread.

Behavior impact:

- Intended behavior change: none.
- Thread name, daemon flag, argument order passed to task functions, coroutine handling,
  heartbeat start/stop, and runtime thread cleanup remain unchanged.
- The heartbeat thread path is untouched.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.

### 2026-06-11 - P5 task update guard helper extraction

Changed:

- Extracted `_should_apply_task_update` from `update_task`.
- Kept the unknown-task guard and cancelled-task overwrite guard as a named internal predicate.

Behavior impact:

- Intended behavior change: none.
- Unknown tasks still return without store updates or log writes.
- Persisted or memory tasks with `cancelled` status still reject later non-cancelled updates.
- Status normalization, memory update, store update, log append, and terminal lock release ordering
  remain unchanged.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.

### 2026-06-11 - P5 running ingestion task match helper extraction

Changed:

- Extracted `_has_ingestion_lock_identity` and `_matches_running_ingestion_task` from
  `find_running_ingestion_task`.
- Kept `exclude_task_id` filtering in `find_running_ingestion_task` before the extracted matcher.

Behavior impact:

- Intended behavior change: none.
- Active status filtering, `ingestion_lock_key` matching, legacy ingestion task-type fallback, and
  normalized group-id comparison remain unchanged.
- Existing lock-conflict behavior for same-group ingestion tasks is preserved.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.

### 2026-06-11 - P5 runtime shutdown active task cancel helper extraction

Changed:

- Extracted `_cancel_active_runtime_tasks` from `request_runtime_shutdown`.
- Kept resource stop requests before task cancellation and runtime tracking cleanup after task
  cancellation.

Behavior impact:

- Intended behavior change: none.
- Active runtime tasks still have persisted stop flags set before `update_task(..., "cancelled",
  "服务关闭，任务已停止")`.
- Shutdown resource stop ordering, log/status behavior, heartbeat cleanup, runtime thread cleanup,
  and SSE cleanup remain unchanged.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py
uv run python -m unittest tests.test_task_runtime_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.

### 2026-06-11 - P5 task runtime status module extraction

Changed:

- Added `backend/services/task_runtime_status.py` for pure task status constants, normalization, and
  task-matching helpers.
- Moved ingestion lock identity checks and latest-task matching helpers out of
  `backend/services/task_runtime.py`.
- Kept the same symbol names imported into `task_runtime.py`, preserving existing internal imports
  such as `_normalize_task`, `_is_active_task_status`, `_is_runtime_terminal_status`, and
  `INGESTION_LOCK_TYPES`.

Behavior impact:

- Intended behavior change: none.
- Public task runtime functions, route behavior, task status normalization, ingestion lock matching,
  latest-task filtering/sorting, fallback memory task behavior, and task store interactions remain
  unchanged.
- This is a module-boundary cleanup only; no storage schema, route response, task ordering, or
  frontend behavior changed.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py backend\services\task_runtime_status.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.
- Combined task runtime/store/routes tests: 57 tests passed, 14 PostgreSQL integration tests
  skipped.

### 2026-06-11 - P5 task runtime log helper module extraction

Changed:

- Added `backend/services/task_runtime_logs.py` for in-memory task log and SSE subscriber dict
  operations.
- Kept `backend/services/task_runtime.py` responsible for locking, persistence, broadcast ordering,
  and public task runtime APIs.

Behavior impact:

- Intended behavior change: none.
- `add_task_log` still persists first, appends the persisted formatted log to memory, then
  broadcasts.
- `get_task_logs_state` still prefers persisted logs over memory logs and still returns a memory log
  copy when persistence is empty.
- Subscribe, unsubscribe, unknown-subscriber handling, unknown-task unsubscribe no-op behavior, and
  failing-subscriber broadcast tolerance remain unchanged.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py backend\services\task_runtime_logs.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.
- Combined task runtime/store/routes tests: 57 tests passed, 14 PostgreSQL integration tests
  skipped.

### 2026-06-11 - P5 task runtime memory helper module extraction

Changed:

- Added `backend/services/task_runtime_memory.py` for in-memory task state construction, lookup,
  snapshot, update, and update-guard predicates.
- Kept the `current_tasks` compatibility dict in `backend/services/task_runtime.py`; only the dict
  operations moved.

Behavior impact:

- Intended behavior change: none.
- Ordinary task creation, ingestion task creation, memory fallback reads, shutdown snapshots,
  unknown-task update no-op behavior, cancelled-task overwrite protection, and memory result updates
  remain unchanged.
- Public task runtime functions and direct access to `task_runtime.current_tasks` remain available.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py backend\services\task_runtime_memory.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.
- Combined task runtime/store/routes tests: 57 tests passed, 14 PostgreSQL integration tests
  skipped.

### 2026-06-11 - P5 task runtime resource helper module extraction

Changed:

- Added `backend/services/task_runtime_resources.py` for crawler/downloader resource registry
  operations and stop-flag requests.
- Kept `crawler_instances` and `file_downloader_instances` in
  `backend/services/task_runtime.py` for compatibility with existing tests and file workflow code.
- Preserved `_request_stop_for_resources` and `_request_stop_for_task_resources` as internal
  `task_runtime.py` wrappers.

Behavior impact:

- Intended behavior change: none.
- Registered crawler stop, downloader stop, global crawler fallback stop, runtime shutdown resource
  snapshots, resource tracking cleanup, and objects-without-`set_stop_flag` tolerance remain
  unchanged.
- Public `register_task_crawler`/`unregister_task_crawler` and direct access to
  `task_runtime.crawler_instances` / `task_runtime.file_downloader_instances` remain available.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py backend\services\task_runtime_resources.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.
- Combined task runtime/store/routes tests: 57 tests passed, 14 PostgreSQL integration tests
  skipped.

### 2026-06-11 - P5 task runtime thread helper module extraction

Changed:

- Added `backend/services/task_runtime_threads.py` for runtime task thread and lock-heartbeat dict
  operations.
- Kept thread construction, daemon/thread names, heartbeat loop timing, coroutine execution, and
  shutdown ordering in `backend/services/task_runtime.py`.
- Kept `runtime_task_threads` and `runtime_task_heartbeats` in `task_runtime.py` for existing tests
  and compatibility.

Behavior impact:

- Intended behavior change: none.
- Ingestion heartbeat registration/stop, non-ingestion heartbeat skip, runtime task thread
  registration/removal, async task execution, daemon thread names, and shutdown heartbeat/thread
  cleanup remain unchanged.

Verification:

```powershell
uv run python -m py_compile backend\services\task_runtime.py backend\services\task_runtime_threads.py
uv run python -m unittest tests.test_task_runtime_helpers -v
uv run python -m unittest tests.test_task_runtime_helpers tests.test_task_store tests.test_task_routes_helpers -v
```

Result:

- `py_compile` passed.
- `tests.test_task_runtime_helpers`: 38 tests passed.
- Combined task runtime/store/routes tests: 57 tests passed, 14 PostgreSQL integration tests
  skipped.

### 2026-06-11 - P2 topic comment image loader extraction

Changed:

- Added `load_topic_comment_images_map` to `backend/storage/zsxq_database_helpers.py`.
- Moved the existing `get_topic_detail` comment-image batch query and image row mapping from
  `backend/storage/zsxq_database.py` into the helper.

Behavior impact:

- Intended behavior change: none.
- The comment image query still uses 500-row chunks, the same scoped group condition, the same
  `ORDER BY comment_id ASC, image_id ASC`, the same parameter order, and
  `topic_detail_image_payload(..., offset=1)`.
- Existing `get_topic_detail` comment nesting, repliee, image payload, and scoped-query tests remain
  the behavior lock.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic talk asset loader extraction

Changed:

- Added `load_topic_detail_talk` to `backend/storage/zsxq_database_helpers.py`.
- Moved the existing `get_topic_detail` talk image, topic-file, and article lookup block from
  `backend/storage/zsxq_database.py` into the helper.
- Removed the now-unused direct helper imports from `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- The helper is still called only after a talk row exists.
- The three child queries keep the same SQL predicates, scoped group filters, sort order, parameter
  tuples, and payload builders.
- Existing `get_topic_detail` talk-with-images-files-article and scoped-query tests remain the
  behavior lock.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic engagement loader extraction

Changed:

- Added `load_topic_detail_latest_likes` and `load_topic_detail_likes_detail` to
  `backend/storage/zsxq_database_helpers.py`.
- Replaced the matching latest-like and like-emoji query blocks in
  `backend/storage/zsxq_database.py` with helper calls at the original call sites.
- Removed the now-unused direct payload-builder imports from `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- Query order remains unchanged: latest likes are still read before comments, and like emojis are
  still read after comments.
- SQL predicates, scoped group filters, sort/limit behavior, parameter tuples, and returned payload
  shapes are unchanged.
- Existing engagement tests verify the two query parameter lists and returned payload.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic Q&A loader extraction

Changed:

- Added `load_topic_detail_qa` to `backend/storage/zsxq_database_helpers.py`.
- Moved the existing `get_topic_detail` question and answer lookup block from
  `backend/storage/zsxq_database.py` into the helper.
- Kept the `topic_detail["type"] == "q&a"` guard in `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- Q&A child queries still run only for `q&a` topics.
- The question query, answer query, scoped group filters, parameter tuples, and payload builders are
  unchanged.
- Existing Q&A tests verify the two query parameter lists and returned question/answer payloads.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic comment loader extraction

Changed:

- Added `load_topic_detail_comments` to `backend/storage/zsxq_database_helpers.py`.
- Moved the existing `get_topic_detail` comment list query, comment-id collection, image-map load,
  and nested comment build into the helper.
- Removed the now-unused direct comment helper imports from `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- The comment query still returns all comments, keeps `ORDER BY c.create_time ASC`, and keeps the
  same scoped group predicate and parameter tuple.
- The comment image batch loader and nested comment builder are called in the same order after the
  comment rows are read.
- Existing tests verify scoped child queries, comment-image query params, repliee payloads, and
  nested comment output.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic talk row loader extraction

Changed:

- Added `load_topic_detail_talk_payload` to `backend/storage/zsxq_database_helpers.py`.
- Moved the existing `get_topic_detail` talk-row lookup into the helper, alongside the already
  extracted talk asset loader.
- Kept assignment to `topic_detail["talk"]` in `backend/storage/zsxq_database.py` and guarded it
  with `is not None`.

Behavior impact:

- Intended behavior change: none.
- A talk payload is still attached only when the talk row exists.
- The talk-row query, topic id parameter, downstream image/file/article loaders, and returned payload
  shape are unchanged.
- Existing tests cover both no-talk detail reads and talk reads with images, files, and article.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic detail base loader extraction

Changed:

- Added `load_topic_detail_base` to `backend/storage/zsxq_database_helpers.py`.
- Moved the existing `get_topic_detail` base topic/group query and base payload mapping from
  `backend/storage/zsxq_database.py` into the helper.
- Kept `_topic_detail_scope` and the `None` return for missing topic rows in
  `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- The base query still uses the same generated `WHERE` clause, tuple parameters, selected columns,
  `LEFT JOIN groups`, and base payload builder.
- Missing topic rows still return `None` before any child queries run.
- Existing scoped-query and detail payload tests cover this path.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 19 tests passed.
- Full backend unittest discovery: 557 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build was not rerun because this slice only changes backend storage/helper code.

### 2026-06-11 - P9 download response filename helper extraction

Changed:

- Added characterization coverage for `download_file` using `content-disposition` to replace a
  default `file_...` name with the real response filename.
- Added `response_filename_override` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced the inline response-header filename override block in
  `backend/crawlers/zsxq_file_downloader.py` with the helper call.

Behavior impact:

- Intended behavior change: none.
- The override still runs only when the current name starts with `file_` and the response has a
  `content-disposition` header with a filename.
- Safe filename normalization, final file path, completion status update path, retry loop, stop
  checks, and partial-file cleanup are unchanged.
- No legacy, fallback, signed URL, or retry behavior was removed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 27 tests passed.
- Full backend unittest discovery: 558 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 partial download cleanup helper extraction

Changed:

- Added `remove_partial_download` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Added focused helper coverage for deleting an existing `.part` file and returning `False` for a
  missing path.
- Replaced the conditional `.part` cleanup blocks before writing, on stop, and on download
  exception in `backend/crawlers/zsxq_file_downloader.py`.

Behavior impact:

- Intended behavior change: none.
- The helper still calls `os.remove` only when the partial path exists, so delete errors propagate
  as before.
- The size-mismatch cleanup remains a direct `os.remove(temp_path)` because that path previously
  assumed the `.part` file exists and should continue to enter the existing retry/error flow if
  removal fails.
- No retry, stop, signed URL, status-update, or fallback behavior was removed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 28 tests passed.
- Full backend unittest discovery: 559 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download progress message helper extraction

Changed:

- Added `download_progress_message` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Added focused helper coverage for known-size final progress, non-boundary known-size chunks,
  unknown-size byte logging, and the 10 MB unknown-size boundary.
- Replaced the nested progress-log conditions inside `download_file` with a helper call.

Behavior impact:

- Intended behavior change: none.
- The same progress strings are emitted for known-size downloads at completion or 10 MB intervals.
- Unknown-size downloads still log byte progress only when the chunk total is not exactly on a 10 MB
  boundary, matching the previous branch behavior.
- No download, retry, stop, partial-file cleanup, signed URL, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 30 tests passed.
- Full backend unittest discovery: 561 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download URL failure detail helper extraction

Changed:

- Added `download_url_failure_detail` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Added helper coverage for default failure details, API-provided details, and blank-value fallback.
- Added `download_file` behavior coverage for the no-download-url path and its failed status update.
- Replaced the inline no-download-url error detail construction in `download_file`.

Behavior impact:

- Intended behavior change: none.
- Missing download URLs still mark the file as `failed` without making a body download request.
- The default error code/message remain `download_url_unavailable` and `无法获取下载链接`.
- API-provided details, including numeric codes such as `1030`, are still stringified before storage.
- No retry, signed URL, stop, partial-file cleanup, or fallback behavior was removed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 32 tests passed.
- Full backend unittest discovery: 563 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download retry wait helper extraction

Changed:

- Added `download_retry_wait` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced the inline retry-delay and retry-message construction in `download_file`.
- Added focused helper coverage for the retry delay formula and exact retry log message.

Behavior impact:

- Intended behavior change: none.
- The retry branch still runs only when `attempt > 0`.
- The delay remains `2 * attempt`, and the same log message is emitted before sleeping.
- `time.sleep`, signed URL fetch, body download, partial-file cleanup, and status updates remain in
  the same `download_file` control flow.
- No retry, stop, signed URL, fallback, or status-update behavior was removed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 33 tests passed.
- Full backend unittest discovery: 569 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download interval plan helper extraction

Changed:

- Added `download_interval_plan` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced the inline branch planning inside `_apply_download_intervals` with the helper output.
- Added focused helper coverage for long-sleep, normal interval, and no-sleep branches.
- Added method-level coverage for long-sleep side effects: log order, `time.sleep`, and batch reset.

Behavior impact:

- Intended behavior change: none.
- `_apply_download_intervals` still performs the same side effects in the same order:
  long-sleep log, sleep, reset `current_batch_count`, completion log.
- Normal interval still logs then sleeps only when `download_interval > 0`.
- The no-sleep branch still returns without logging or sleeping.
- No retry, stop, signed URL, partial-file cleanup, fallback, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 36 tests passed.
- Full backend unittest discovery: 572 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download size mismatch helper extraction

Changed:

- Added `download_size_mismatch_detail` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced the inline size-mismatch error code/message construction in `download_file`.
- Added focused helper coverage for mismatch details, expected-size-zero bypass, and exact-size pass.

Behavior impact:

- Intended behavior change: none.
- Size mismatch still uses `size_mismatch` and the same formatted Chinese error message.
- `expected_size <= 0` still bypasses validation.
- Direct `.part` removal and retry `continue` remain in the original `download_file` control flow.
- No retry, stop, signed URL, partial-file cleanup, fallback, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 37 tests passed.
- Full backend unittest discovery: 573 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download HTTP failure detail helper extraction

Changed:

- Added `download_http_failure_detail` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced inline non-200 body-download error code/message construction in `download_file`.
- Added focused helper coverage for the exact `http_status` / `HTTP <status_code>` contract.

Behavior impact:

- Intended behavior change: none.
- Non-200 body download still uses `http_status` and `HTTP <status_code>`.
- Logging, retry-loop continuation, final failed status update, and partial-file cleanup behavior remain unchanged.
- No retry, stop, signed URL, fallback, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 38 tests passed.
- Full backend unittest discovery: 574 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download exception detail helper extraction

Changed:

- Added `download_exception_detail` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced inline body-download exception error code/message construction in `download_file`.
- Added focused helper coverage for the exact `download_exception` / `str(exc)` contract.

Behavior impact:

- Intended behavior change: none.
- Body-download exceptions still use `download_exception` and the exception string as the failed status detail.
- Exception logging, retry-loop continuation, partial-file cleanup, and final failed status update remain unchanged.
- Empty exception strings still flow through the existing final `last_error or "文件下载失败"` fallback.
- No retry, stop, signed URL, fallback, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 39 tests passed.
- Full backend unittest discovery: 575 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download final failure detail helper extraction

Changed:

- Added `download_final_failure_detail` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced inline final failed-status error code/message fallbacks in `download_file`.
- Added focused helper coverage for `None`, empty-string, and existing-error branches.

Behavior impact:

- Intended behavior change: none.
- Missing or empty `last_error_code` still falls back to `download_failed`.
- Missing or empty `last_error` still falls back to `文件下载失败`.
- Existing body-download error code/message values remain unchanged.
- Final failed status update call, retry exhaustion logging, and all retry/cleanup behavior remain unchanged.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 40 tests passed.
- Full backend unittest discovery: 576 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download expected size helper extraction

Changed:

- Added `download_expected_size` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced inline expected-size calculation in the body-download size validation path.
- Added focused helper coverage for positive metadata size, zero size, and negative size branches.

Behavior impact:

- Intended behavior change: none.
- Positive file metadata size still takes precedence over response `content-length`.
- Zero or negative file metadata size still falls back to response `content-length`.
- Size mismatch detection, retry continuation, `.part` cleanup, and final status updates remain unchanged.
- No retry, stop, signed URL, fallback, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 41 tests passed.
- Full backend unittest discovery: 577 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download total size helper extraction

Changed:

- Added `download_total_size` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced inline response `content-length` parsing in the body-download path.
- Added focused helper coverage for present, missing, and invalid `content-length` values.

Behavior impact:

- Intended behavior change: none.
- Present `content-length` values are still parsed with `int(...)`.
- Missing `content-length` still defaults to `0`.
- Invalid `content-length` values still raise `ValueError`, preserving the existing body-download
  exception/retry path.
- No retry, stop, signed URL, partial-file cleanup, fallback, or status-update behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 42 tests passed.
- Full backend unittest discovery: 578 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 partial download path helper extraction

Changed:

- Added `partial_download_path` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Replaced duplicated `.part` path construction in the body-download write path and exception
  cleanup path.
- Added focused helper coverage for suffix construction.

Behavior impact:

- Intended behavior change: none.
- Temporary download files still append `.part` to the current `file_path`.
- The helper is still called at the original locations, so filename overrides continue to affect
  subsequent partial-path calculation exactly as before.
- Partial-file cleanup, size-mismatch removal, final `os.replace`, retry, stop, fallback, and
  status-update behavior remain unchanged.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 43 tests passed.
- Full backend unittest discovery: 579 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P9 download stop handler extraction

Changed:

- Added `_handle_download_stop` to `backend/crawlers/zsxq_file_downloader.py`.
- Replaced the inline in-loop stop side-effect block with the private handler.
- Added focused handler coverage for stopped status detail, log message, and partial-file cleanup.

Behavior impact:

- Intended behavior change: none.
- The in-loop stop branch still logs `🛑 下载过程中被停止`, writes failed status with `stopped` /
  `下载过程中被停止`, then attempts partial-file cleanup before returning `False`.
- The handler is called at the original stop-check point inside the chunk loop, so retry, signed URL,
  progress, file write, fallback, and status-update behavior remain unchanged.
- This slice intentionally does not change the existing Windows open-file deletion behavior in the
  stop path; that would be a bug fix requiring a separate risk note and behavior-level test.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 44 tests passed.
- Full backend unittest discovery: 580 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend crawler/helper code.

### 2026-06-11 - P3 columns database helper module split

Changed:

- Added `backend/storage/zsxq_columns_database_helpers.py` for pure column storage row mappers,
  stats defaults, and group-id scope helpers.
- Re-exported the moved helpers from `backend/storage/zsxq_columns_database.py` via imports so
  existing internal/test import paths continue to work.
- Left all SQL, connection setup, commits, runtime DDL no-op behavior, and public methods in
  `backend/storage/zsxq_columns_database.py`.

Behavior impact:

- Intended behavior change: none.
- Existing helper tests still import from `backend.storage.zsxq_columns_database`, proving the old
  module-level helper names remain available.
- Row payload shapes, boolean normalization, group-id coercion, scoped query params, and independent
  stats dict behavior are covered by existing tests.
- No schema, compatibility, fallback, or runtime storage behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 16 tests passed.
- Full backend unittest discovery: 563 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 pending queue query helper extraction

Changed:

- Added `_pending_videos_query`, `_pending_files_query`, and `_uncached_images_query` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Added focused coverage for scoped and unscoped query branches.
- Replaced the inline SQL branches in `get_pending_videos`, `get_pending_files`, and
  `get_uncached_images` with helper calls.

Behavior impact:

- Intended behavior change: none.
- The truthy `group_id` behavior is preserved: only truthy group ids add `AND td.group_id = ?`.
- Unscoped branches still execute without a params tuple.
- Returned row mapping and queue payload shapes are unchanged.
- No schema, compatibility, fallback, status, or commit behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 18 tests passed.
- Full backend unittest discovery: 565 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 stats count query helper extraction

Changed:

- Added `_stats_count_queries` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the repeated count-query block in `get_stats` with a loop over the helper output.
- Added focused characterization coverage for statistics query key order, group filter params,
  completed-download filters, and returned stats shape.

Behavior impact:

- Intended behavior change: none.
- `get_stats` still initializes from `_empty_stats`, executes the same 9 count queries in the
  same order, and writes the same statistics keys.
- Query params remain `(group_id,)` for every count query.
- Error behavior is unchanged: query or fetch failures still propagate from the same call path.
- No schema, compatibility, fallback, status, or commit behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 20 tests passed.
- Full backend unittest discovery: 567 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic comment nesting helper extraction

Changed:

- Added `_nest_topic_comments` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the in-method parent/child assembly block in `get_topic_comments` with the helper call.
- Added characterization coverage for parent order, children that appear before their parent, child
  attachment order, and orphan child behavior.

Behavior impact:

- Intended behavior change: none.
- SQL query order and comment-image lookup side effects remain inside `get_topic_comments`.
- Nested comment assembly preserves the existing behavior: only comments without a truthy
  `parent_comment_id` are returned at the top level, children are attached after all comments are
  read, and orphan children are not returned as top-level comments.
- No schema, compatibility, fallback, status, or commit behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 21 tests passed.
- Full backend unittest discovery: 568 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 crawl log update helper extraction

Changed:

- Added `_crawl_log_update_parts` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the inline dynamic update-field assembly in `update_crawl_log` with the helper call.
- Added characterization coverage for update field order, value order, falsy update semantics,
  terminal-status `end_time` handling, and the no-op path when no update parts exist.

Behavior impact:

- Intended behavior change: none.
- `update_crawl_log` still ignores falsy counts, empty status, and empty error messages.
- `completed` and `failed` statuses still add `end_time = CURRENT_TIMESTAMP` without adding a
  parameter value.
- The method still appends `log_id`, executes the same `UPDATE crawl_log SET ... WHERE id = ?`
  statement only when at least one update part exists, and commits only after that execute.
- No schema, compatibility, fallback, status value, or commit-order behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 24 tests passed.
- Full backend unittest discovery: 583 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 unused datetime import cleanup

Changed:

- Removed the unused `datetime` import from `backend/storage/zsxq_columns_database.py`.

Behavior impact:

- Intended behavior change: none.
- Static search showed `datetime` only appeared on the import line in this module.
- No storage method, SQL text, commit behavior, compatibility layer, fallback path, or public
  import surface was changed.

Verification:

```powershell
rg -n "datetime|^from datetime" backend\storage\zsxq_columns_database.py
uv run python -m py_compile backend\storage\zsxq_columns_database.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- Static search before deletion found only `from datetime import datetime`.
- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 24 tests passed.
- Full backend unittest discovery: 583 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only removes an unused backend import.

### 2026-06-11 - P3 clear-data helper extraction

Changed:

- Added `_empty_clear_data_stats` and `_topic_child_delete_statements` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the inline clear-data stats literal and repeated topic child-delete statements in
  `clear_all_data`.
- Added characterization coverage for stats key order, independent stats dicts, topic child-delete
  order, `topic_owners` non-counted behavior, method-level SQL order, rowcount-to-stats mapping,
  rollback absence on success, and commit count.

Behavior impact:

- Intended behavior change: none.
- `clear_all_data` still selects topic ids first, then deletes comments, videos, files, images, and
  topic owners in the same order when topic ids exist.
- `topic_owners` deletion still has no returned stats counter.
- Group-scoped deletes for topic details, column topics, columns, and crawl logs still run after
  topic child deletes.
- Success still commits once and returns the same stats shape; failure behavior and rollback path
  were not changed.
- No schema, compatibility layer, fallback path, or public API behavior was changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 26 tests passed.
- Full backend unittest discovery: 585 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 group clear delete helper extraction

Changed:

- Added `_group_clear_delete_statements` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the remaining group-scoped delete block in `clear_all_data` with a helper-driven loop.
- Extended clear-data helper coverage to lock group delete order and the non-counted crawl-log
  delete entry.

Behavior impact:

- Intended behavior change: none.
- `clear_all_data` still deletes topic details, column topics, columns, and crawl logs in the same
  order after topic child deletes.
- Returned stats still count `details_deleted`, `topics_deleted`, and `columns_deleted`; crawl-log
  deletion still has no returned stats counter.
- The existing method-level test continues to prove SQL order, rowcount-to-stats mapping, commit
  count, and rollback absence on success.
- No schema, compatibility layer, fallback path, public API behavior, or deletion side effect was
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 26 tests passed.
- Full backend unittest discovery: 585 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 media insert params helper extraction

Changed:

- Added `_topic_image_insert_params`, `_topic_file_insert_params`, and `_topic_video_insert_params`
  to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline media insert parameter tuples in `_insert_image`, `_insert_file`, and
  `_insert_video`.
- Added characterization coverage for image/file/video insert column order, missing nested media
  defaults, file-name/download-count defaults, and missing-id skip behavior.

Behavior impact:

- Intended behavior change: none.
- The SQL text, conflict update clauses, method signatures, and missing-id early returns are
  unchanged.
- Media insert helpers preserve the original tuple order and default values: missing image nested
  objects produce `None` fields, missing file name becomes `""`, missing download count becomes
  `0`, and missing video cover fields become `None`.
- No commit behavior, schema, compatibility layer, fallback path, or public API behavior was
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 28 tests passed.
- Full backend unittest discovery: 587 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 comment insert params helper extraction

Changed:

- Added `_topic_comment_insert_params` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the inline comment insert parameter tuple in `_insert_comment`.
- Added characterization coverage for comment insert column order, default values, full method-level
  parameter shape, and missing-`comment_id` skip behavior.

Behavior impact:

- Intended behavior change: none.
- `_insert_comment` still returns early when `comment_data` or `comment_id` is missing.
- `owner` and `repliee` are still inserted before resolving `group_id`, preserving side-effect
  order.
- The SQL text, conflict update clause, method signature, group-id fallback behavior, and default
  values are unchanged.
- No schema, compatibility layer, fallback path, public API behavior, or commit behavior was
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 29 tests passed.
- Full backend unittest discovery: 588 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 column/topic/user insert params helper extraction

Changed:

- Added `_column_insert_params`, `_column_topic_insert_params`, and `_user_insert_params` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline insert parameter tuples in `insert_column`, `insert_column_topic`, and
  `insert_user`.
- Added characterization coverage for insert column order, default values, missing-ID skip paths,
  commit counts, and `insert_user`'s existing no-commit behavior.

Behavior impact:

- Intended behavior change: none.
- `insert_column` and `insert_column_topic` still return `None` without SQL or commit when the
  required ID is missing.
- `insert_column` and `insert_column_topic` still commit once after successful insert/update.
- `insert_user` still returns `None` without SQL when `user_id` is missing and still does not
  commit on success.
- SQL text, conflict update clauses, method signatures, default values, schema, compatibility
  layer, fallback path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 32 tests passed.
- Full backend unittest discovery: 591 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic detail insert params helper extraction

Changed:

- Added `_topic_detail_insert_params` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the inline `topic_details` insert parameter tuple in `insert_topic_detail`.
- Added characterization coverage for topic-detail insert column order, `talk.text` extraction,
  default values, raw JSON placement, missing-`topic_id` skip behavior, and successful commit count.

Behavior impact:

- Intended behavior change: none.
- `insert_topic_detail` still returns `None` without SQL or commit when `topic_id` is missing.
- `topic_data.get('talk', {})` behavior is preserved, including the existing expectation that a
  present `talk` value is mapping-like.
- Owner, image, file, content-voice, video, and comment processing still runs after the
  `topic_details` insert in the same order.
- SQL text, conflict update clause, method signature, default values, raw JSON storage, schema,
  compatibility layer, fallback path, public API behavior, and commit behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 34 tests passed.
- Full backend unittest discovery: 593 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic owner insert helper extraction

Changed:

- Added `_topic_owner_insert_params` to `backend/storage/zsxq_columns_database_helpers.py`.
- Extracted `_insert_topic_owner` from `insert_topic_detail`.
- Replaced inline `topic_owners` insert parameters with the helper.
- Added characterization coverage for owner insert parameter order, no-owner skip behavior,
  `insert_user` returning no ID, topic-owner SQL, and the full related insert order after
  `topic_details`.

Behavior impact:

- Intended behavior change: none.
- `insert_topic_detail` still writes `topic_details` first, then owner, images, files,
  `content_voice`, video, comments, and finally commits in the same order.
- `_insert_topic_owner` preserves the existing skip behavior for missing/falsy `talk.owner`.
- `insert_user` is still called before `topic_owners` insert and a falsy returned user ID still
  suppresses the owner relation insert.
- SQL text, conflict update clause, method signatures, default values, schema, compatibility
  layer, fallback path, public API behavior, and commit behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 37 tests passed.
- Full backend unittest discovery: 596 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic related payload helper extraction

Changed:

- Extracted `_insert_topic_related_payloads` from `insert_topic_detail`.
- Added characterization coverage for the new helper's empty-payload skip behavior and
  image/file/content-voice/video/comment write order.

Behavior impact:

- Intended behavior change: none.
- `insert_topic_detail` still writes `topic_details`, topic owner, images, files,
  `content_voice`, video, comments, and then commits in the same order.
- Empty image/file/comment lists and missing optional `content_voice`/video values still produce
  no related insert calls.
- SQL text, insert parameter helpers, method signatures, schema, compatibility layer, fallback
  path, public API behavior, and commit behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 38 tests passed.
- Full backend unittest discovery: 597 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 download status update helper extraction

Changed:

- Added `_video_download_status_update` and `_file_download_status_update` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline SQL branches in `update_video_download_status` and `update_file_download_status`
  with helper-generated SQL/params.
- Added characterization coverage for truthy branch selection, empty-string behavior, SQL params,
  group-id normalization at the method boundary, and commit counts.

Behavior impact:

- Intended behavior change: none.
- `local_path` still controls whether video/file updates set local path and download time.
- `video_url` still controls the intermediate video update branch only when no truthy
  `local_path` exists.
- Empty strings still follow the old falsy branches.
- Method signatures, commit behavior, SQL semantics, schema, compatibility layer, fallback path,
  and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 40 tests passed.
- Full backend unittest discovery: 599 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic attachment query helper extraction

Changed:

- Added `_topic_images_query`, `_topic_files_query`, and `_topic_videos_query` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline attachment SQL in `get_topic_images`, `get_topic_files`, and `get_topic_videos`
  with helper-generated SQL/params.
- Added characterization coverage for scoped and unscoped params, selected columns, group-scope
  predicates, and method-level use of `self.group_id`.

Behavior impact:

- Intended behavior change: none.
- The attachment methods still normalize scope through `_scope_group_id_param`, execute the same
  topic-scoped SQL, and map rows with the existing row mappers.
- Scoped calls still pass `(topic_id, scope_group_id, scope_group_id)`; unscoped calls still pass
  `(topic_id, None, None)`.
- Return shapes, SQL semantics, method signatures, schema, compatibility layer, fallback path, and
  public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 41 tests passed.
- Full backend unittest discovery: 600 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 comment image query helper extraction

Changed:

- Added `_comment_images_query` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline comment-image SQL in `get_topic_comments` with helper-generated SQL/params.
- Added characterization coverage for the helper query, topic filter params, parent comment image
  attachment, child-comment image query execution, and nested reply shape.

Behavior impact:

- Intended behavior change: none.
- `get_topic_comments` still runs the main comment query first, then runs one image query per
  comment in returned order, only attaching an `images` field when rows exist.
- The comment-image query still uses `(comment_id, scope_group_id, topic_id)` and preserves the
  existing `(? IS NULL OR topic_id = ?)` filter.
- Return shapes, nested reply behavior, SQL semantics, method signatures, schema, compatibility
  layer, fallback path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 43 tests passed.
- Full backend unittest discovery: 603 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic comments query helper extraction

Changed:

- Added `_topic_comments_query` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline main-comment SQL in `get_topic_comments` with helper-generated SQL/params.
- Added characterization coverage for selected fields, owner/repliee joins, group-scope params,
  and `ORDER BY c.create_time ASC`.

Behavior impact:

- Intended behavior change: none.
- `get_topic_comments` still normalizes scope first, executes the same main comment query, then
  performs the per-comment image queries and nesting logic unchanged.
- Scoped calls still pass `(topic_id, scope_group_id, scope_group_id)`; unscoped calls still pass
  `(topic_id, None, None)`.
- Return shapes, nested reply behavior, image attachment behavior, SQL semantics, method signature,
  schema, compatibility layer, fallback path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 44 tests passed.
- Full backend unittest discovery: 604 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic detail query helper extraction

Changed:

- Added `_topic_detail_query` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline `get_topic_detail` SQL with helper-generated SQL/params.
- Added characterization coverage for selected fields, owner join, `owner_type = 'talk'`, users
  join, and group-scope params.

Behavior impact:

- Intended behavior change: none.
- `get_topic_detail` still normalizes scope first, executes the same detail query, maps rows with
  `_topic_detail_row_to_dict`, then loads images, files, videos, and comments in the same order.
- Scoped calls still pass `(topic_id, scope_group_id, scope_group_id)`; unscoped calls still pass
  `(topic_id, None, None)`.
- Return shapes, child read order, SQL semantics, method signature, schema, compatibility layer,
  fallback path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 45 tests passed.
- Full backend unittest discovery: 605 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 column query helper extraction

Changed:

- Added `_columns_query`, `_column_query`, and `_column_topics_query` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline SQL in `get_columns`, `get_column`, and `get_column_topics` with
  helper-generated SQL/params.
- Added characterization coverage for selected fields, detail join, group-scope params, and
  `ORDER BY` clauses.

Behavior impact:

- Intended behavior change: none.
- `get_columns` still passes the caller-provided `group_id` directly and orders by
  `create_time DESC`.
- `get_column` and `get_column_topics` still normalize scope at the method boundary before
  building SQL params.
- `get_column_topics` still preserves the `topic_details` join on both `topic_id` and `group_id`,
  `has_detail` expression, and `attached_to_column_time DESC` ordering.
- Return shapes, row mappers, SQL semantics, method signatures, schema, compatibility layer,
  fallback path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 47 tests passed.
- Full backend unittest discovery: 607 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 column/user insert statement helper extraction

Changed:

- Added `_column_insert_statement`, `_column_topic_insert_statement`, and
  `_user_insert_statement` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline insert SQL in `insert_column`, `insert_column_topic`, and `insert_user` with
  helper-returned SQL.
- Added characterization coverage for target tables, column order, conflict keys, and update
  fields.

Behavior impact:

- Intended behavior change: none.
- Existing parameter helpers still build the execute params, and method-level skip behavior is
  unchanged.
- `insert_column` and `insert_column_topic` still commit after successful execute; `insert_user`
  still does not commit.
- Return values, SQL upsert semantics, method signatures, schema, compatibility layer, fallback
  path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 49 tests passed.
- Full backend unittest discovery: 609 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic detail/owner insert statement helper extraction

Changed:

- Added `_topic_detail_insert_statement` and `_topic_owner_insert_statement` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline `topic_details` and `topic_owners` insert SQL in `insert_topic_detail` and
  `_insert_topic_owner` with helper-returned SQL.
- Added characterization coverage for `CURRENT_TIMESTAMP`, owner type, conflict keys, and update
  fields.

Behavior impact:

- Intended behavior change: none.
- Existing parameter helpers still build the execute params for both statements.
- `insert_topic_detail` still writes the topic row, then owner, then related payloads, then commits
  once.
- `_insert_topic_owner` still inserts only when `insert_user` returns a truthy user id, and still
  uses owner type `talk`.
- Return values, SQL upsert semantics, write order, commit behavior, method signatures, schema,
  compatibility layer, fallback path, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 51 tests passed.
- Full backend unittest discovery: 611 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 topic media/comment insert statement helper extraction

Changed:

- Added `_topic_image_insert_statement`, `_topic_file_insert_statement`,
  `_topic_video_insert_statement`, and `_topic_comment_insert_statement` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline insert SQL in `_insert_image`, `_insert_file`, `_insert_video`, and
  `_insert_comment` with helper-returned SQL.
- Added characterization coverage for target tables, column order, conflict keys, and update
  fields.

Behavior impact:

- Intended behavior change: none.
- Existing parameter helpers still build all execute params.
- `_insert_comment` still inserts owner and repliee users first, resolves group id the same way,
  then writes the comment row.
- Missing-id skip behavior, related payload write order, `import_comments` commit behavior, SQL
  upsert semantics, method signatures, schema, compatibility layer, fallback path, and public API
  behavior are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 53 tests passed.
- Full backend unittest discovery: 613 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 local path update helper extraction

Changed:

- Added `_video_cover_path_update` and `_image_local_path_update` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline local-cache path update SQL in `update_video_cover_path` and
  `update_image_local_path` with helper-returned SQL.
- Added characterization coverage for SQL shape, parameter order, execute calls, and commit
  counts.

Behavior impact:

- Intended behavior change: none.
- Both public methods keep the same signatures, execute one SQL statement, pass parameters in the
  same order, and commit once per call.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 55 tests passed.
- Full backend unittest discovery: 615 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 incremental SELECT query helper extraction

Changed:

- Added `_topic_group_id_query`, `_topic_detail_exists_query`, and `_group_topic_ids_query` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline SELECT statements in `_resolve_topic_group_id`, `topic_detail_exists`,
  `get_existing_topic_ids`, and the topic-id prefetch in `clear_all_data`.
- Added characterization coverage for SQL shape, parameter order, fetchone/fetchall behavior, and
  `_resolve_topic_group_id` exception fallback.

Behavior impact:

- Intended behavior change: none.
- `_resolve_topic_group_id` still prefers `self.group_id`, still avoids storage reads in that
  branch, and still returns `None` when the lookup fails.
- `topic_detail_exists` still returns `True` for any fetched row and `False` for no row.
- `get_existing_topic_ids` and `clear_all_data` still fetch the same group-scoped topic ids before
  downstream set/delete behavior.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 58 tests passed.
- Full backend unittest discovery: 618 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 crawl log insert statement helper extraction

Changed:

- Added `_crawl_log_insert_statement` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced inline `crawl_log` insert SQL in `start_crawl_log` with helper-returned SQL.
- Added characterization coverage for SQL shape, `RETURNING id`, execute params, commit behavior,
  and the no-return-row `None` branch.

Behavior impact:

- Intended behavior change: none.
- `start_crawl_log` still passes `(group_id, crawl_type)`, fetches one row, commits once, returns
  the returned id when present, and returns `None` when no row is returned.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.
- The dynamic `update_crawl_log` SQL remains intentionally untouched for a separate risk review.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 60 tests passed.
- Full backend unittest discovery: 620 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P3 crawl log update statement helper extraction

Changed:

- Added `_crawl_log_update_statement` to `backend/storage/zsxq_columns_database_helpers.py`.
- Replaced the inline dynamic `crawl_log` update SQL in `update_crawl_log` with helper-returned
  SQL.
- Added characterization coverage for dynamic `SET` clause order, `end_time` placement, list
  parameter shape, execute SQL, and commit behavior.

Behavior impact:

- Intended behavior change: none.
- `_crawl_log_update_parts` still controls which fields are present and their value order.
- `update_crawl_log` still no-ops when there are no update parts, still appends `log_id` to the
  same values list, and still commits once only after executing an update.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_columns_database_helpers`: 62 tests passed.
- Full backend unittest discovery: 622 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic/file existence query helper extraction

Changed:

- Added `topic_exists_query` and `file_exists_query` to
  `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced duplicate-topic detection in `import_topic_data` and file-existence detection in
  `backfill_topic_files_to_core_tables` with helper-returned SQL and params.
- Added characterization coverage for SQL shape, `group_id_param` semantics, existing-topic skip
  behavior, file-sync side effect, and no-commit/no-rollback behavior in the duplicate-topic path.

Behavior impact:

- Intended behavior change: none.
- The existing `group_id_param(None) -> ""` behavior is preserved for both existence queries.
- Existing-topic imports still return `True`, still sync talk files when present, still print the
  skip message, and still avoid the normal import write path.
- Backfill still checks whether a file already exists before deciding whether to increment
  `new_files`.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 21 tests passed.
- Full backend unittest discovery: 624 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic group lookup query helper extraction

Changed:

- Added `topic_group_id_query` to `backend/storage/zsxq_database_helpers.py`, with a compatibility
  wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline topic group-id lookup SQL in `_resolve_topic_group_id` with helper-returned SQL
  and params.
- Added characterization coverage for explicit group priority, runtime group priority, database
  lookup, missing row fallback, exception fallback, SQL shape, and parameter order.

Behavior impact:

- Intended behavior change: none.
- `_resolve_topic_group_id` still uses `explicit_group_id or self.group_id` before querying.
- It still casts numeric group ids via `_nullable_group_id_param`, still returns `None` when no
  topic group is found, and still swallows lookup exceptions by returning `None`.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 22 tests passed.
- Full backend unittest discovery: 625 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 topic timestamp query helper extraction

Changed:

- Added `newest_topic_create_time_query`, `oldest_topic_create_time_query`, and `topic_count_query`
  to `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced inline topic timestamp/count SQL in `get_timestamp_range_info`,
  `get_oldest_topic_timestamp`, and `get_newest_topic_timestamp` with helper-returned SQL and
  params.
- Added characterization coverage for SQL order direction, count SQL shape, range response shape,
  range call order, nullable scope params, and the legacy empty-group params used by the single
  newest/oldest timestamp methods.

Behavior impact:

- Intended behavior change: none.
- `get_timestamp_range_info` still uses nullable group scope for newest, oldest, and count queries,
  preserving unscoped behavior when `group_id` is empty or missing.
- `get_oldest_topic_timestamp` and `get_newest_topic_timestamp` still use the legacy
  `group_id_param(None) -> ""` behavior rather than nullable unscoped behavior.
- All three methods keep their existing return shapes and exception fallback behavior.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 25 tests passed.
- Full backend unittest discovery: 628 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-11 - P2 article topic create-time query helper extraction

Changed:

- Added `topic_create_time_by_id_query` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline article create-time lookup SQL in `_upsert_article` with helper-returned SQL and
  params.
- Added characterization coverage for SQL shape, params, empty article payload skip behavior, topic
  `create_time` lookup, and `INSERT INTO articles` params using the fetched topic time as
  `created_at`.

Behavior impact:

- Intended behavior change: none.
- `_upsert_article` still returns before any database call when both title and article id are empty.
- Article `created_at` still comes from `topics.create_time` when present and still falls back to an
  empty string when the topic row is missing.
- The article insert/upsert statement, conflict target, params order, and update assignments were
  not changed.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 26 tests passed.
- Full backend unittest discovery: 629 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 tag upsert statement helper extraction

Changed:

- Added `tag_id_by_name_query`, `update_tag_hid_statement`, and `insert_tag_statement` to
  `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced inline tag lookup, hid update, and tag insert SQL in `_upsert_tag` with helper-returned
  SQL and params.
- Added characterization coverage for SQL shape, params, existing-tag return, optional hid update,
  insert `RETURNING tag_id`, generated `created_at` format, and the existing missing-return-row
  `None` branch.

Behavior impact:

- Intended behavior change: none.
- `_upsert_tag` still returns the existing tag id, still updates `hid` only when a new `hid` value
  is provided, still inserts new tags with Beijing-time `created_at`, and still returns `None` when
  an insert produces no returned row.
- The tag insert columns, `RETURNING tag_id`, lookup keys, exception fallback, and public method
  signature were not changed.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 28 tests passed.
- Full backend unittest discovery: 631 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 tag link statement helper extraction

Changed:

- Added `insert_topic_tag_statement` and `refresh_tag_topic_count_statement` to
  `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced inline topic-tag insert and tag topic-count refresh SQL in `_link_topic_tag` with
  helper-returned SQL and params.
- Added characterization coverage for SQL shape, params, generated Beijing-time `created_at`,
  insert-before-count-refresh call order, and the existing exception-swallowing print path.

Behavior impact:

- Intended behavior change: none.
- `_link_topic_tag` still inserts `(topic_id, tag_id, created_at)` with
  `ON CONFLICT(topic_id, tag_id) DO NOTHING`, then refreshes `tags.topic_count` from
  `topic_tags`.
- It still has no return value and still catches exceptions by printing `关联话题标签失败: ...`
  without re-raising.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 29 tests passed.
- Full backend unittest discovery: 632 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 tag read query helper extraction

Changed:

- Added `tags_by_group_query`, `topics_by_tag_query`, and `topic_count_by_tag_query` to
  `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced inline SQL in `get_tags_by_group` and `get_topics_by_tag` with helper-returned SQL and
  params.
- Added characterization coverage for tag-list query shape, tagged-topic query shape, count query
  shape, formatted tag rows, tagged-topic pagination, and the existing tagged-topic exception
  fallback response.

Behavior impact:

- Intended behavior change: none.
- `get_tags_by_group` still orders by `topic_count DESC, tag_name ASC`, still formats rows through
  `_format_tag_row`, and still returns `[]` after printing on exceptions.
- `get_topics_by_tag` still computes `offset = (page - 1) * per_page`, returns the same topic row
  shape through `_format_tag_topic_row`, still queries `topic_tags` for total count, and still
  returns an empty topics list plus zero-total pagination on exceptions.
- No schema, config, compatibility, fallback, error handling, logging, or public API semantics were
  changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 33 tests passed.
- Full backend unittest discovery: 636 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 group/user insert statement helper extraction

Changed:

- Added `group_insert_statement` and `user_insert_statement` to
  `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO groups` and `INSERT INTO users` statements in `_upsert_group` and
  `_upsert_user` with helper-returned SQL and params.
- Added characterization coverage for helper SQL shape, parameter defaults, missing-id skip
  behavior, generated Beijing-time `created_at` format, and execute params.

Behavior impact:

- Intended behavior change: none.
- `_upsert_group` still returns before any database call when `group_id` is missing, still writes
  the same group columns, and still updates the same fields on `ON CONFLICT(group_id)`.
- `_upsert_user` still returns before any database call when `user_id` is missing, still writes the
  same user columns, preserves empty-string defaults, and still updates the same fields on
  `ON CONFLICT(user_id)`.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string
  generated in the calling methods.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 35 tests passed.
- Full backend unittest discovery: 638 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic insert statement helper extraction

Changed:

- Added `topic_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO topics` SQL and params in `_upsert_topic` with helper-returned SQL
  and params.
- Added characterization coverage for helper SQL shape, full parameter order, missing-topic skip
  behavior, default field values, and generated Beijing-time `imported_at` format.

Behavior impact:

- Intended behavior change: none.
- `_upsert_topic` still returns before any database call when `topic_id` is missing.
- It still writes the same `topics` columns, preserves the original nested `group.group_id`
  extraction, keeps the existing default values, and updates the same fields on
  `ON CONFLICT(topic_id)`.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string
  generated in `_upsert_topic`.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 37 tests passed.
- Full backend unittest discovery: 640 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic stats update statement helper extraction

Changed:

- Added `topic_stats_update_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `UPDATE topics` SQL and params in `update_topic_stats` with helper-returned SQL
  and params.
- Added characterization coverage for helper SQL shape, parameter order, `user_specific` boolean
  mapping, missing-topic skip behavior, rowcount success and warning branches, exception fallback,
  generated Beijing-time `imported_at` format, and the existing `group_id=None -> ""` scope params.

Behavior impact:

- Intended behavior change: none.
- `update_topic_stats` still returns `False` before any database call when `topic_id` is missing.
- It still updates only the stats/user-specific fields plus `imported_at`, still checks
  `cursor.rowcount`, still prints the same not-found warning, and still catches exceptions by
  printing and returning `False`.
- Group scope parameter semantics are preserved, including the legacy `_group_id_param(None) -> ""`
  behavior for this method.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 39 tests passed.
- Full backend unittest discovery: 642 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 talk insert statement helper extraction

Changed:

- Added `talk_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO talks` SQL and params in `_upsert_talk` with helper-returned SQL
  and params.
- Added characterization coverage for helper SQL shape, parameter order, empty payload skip,
  missing `owner.user_id` skip, and generated Beijing-time `created_at` format.

Behavior impact:

- Intended behavior change: none.
- `_upsert_talk` still returns before any database call when `talk_data` is empty or
  `owner.user_id` is missing/falsy.
- It still writes the same `talks` columns, preserves the original `owner.user_id` extraction,
  keeps the existing empty-string default for `text`, and updates the same fields on
  `ON CONFLICT(topic_id)`.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string
  generated in `_upsert_talk`.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 41 tests passed.
- Full backend unittest discovery: 644 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 image insert statement helper extraction

Changed:

- Added `image_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced duplicated inline `INSERT INTO images` SQL and params in `_upsert_image` and
  `_import_comment_images` with helper-returned SQL and params.
- Added characterization coverage for helper SQL shape, full parameter order, missing-image skip,
  generated Beijing-time `created_at` format, and the two historical numeric-default paths.

Behavior impact:

- Intended behavior change: none.
- `_upsert_image` still returns before any database call when `image_id` is missing/falsy.
- `_import_comment_images` still skips individual images without `image_id` and continues the loop.
- Both paths still write the same `images` columns and update the same fields on
  `ON CONFLICT(image_id)`.
- The duplicated SQL was unified, but the historical default difference is preserved explicitly:
  `_upsert_image` keeps missing width/height/size values as `None`, while `_import_comment_images`
  keeps missing width/height/size values as `0`.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string
  generated in the calling methods.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 43 tests passed.
- Full backend unittest discovery: 646 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 likes import statement helper extraction

Changed:

- Added `delete_latest_likes_statement`, `like_insert_statement`, and
  `latest_like_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with compatibility
  wrappers in `backend/storage/zsxq_database.py`.
- Replaced inline `latest_likes` delete SQL plus `likes` and `latest_likes` insert SQL in
  `_import_likes` with helper-returned SQL and params.
- Added characterization coverage for helper SQL shape, parameter order, field-missing skip,
  empty `latest_likes` delete behavior, missing `owner.user_id` skip, write order, and generated
  Beijing-time timestamp format.

Behavior impact:

- Intended behavior change: none.
- `_import_likes` still returns before any database call when the `latest_likes` key is absent.
- When `latest_likes` is present, it still deletes existing `latest_likes` rows for the topic before
  processing the payload, including the empty-list case.
- Individual likes without a truthy `owner.user_id` are still skipped.
- Valid likes still write one historical `likes` row and one conflict-upserted `latest_likes` row,
  in the same order, with the same `create_time` default of an empty string.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string
  generated inside the per-like branch.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 45 tests passed.
- Full backend unittest discovery: 648 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 like emoji insert statement helper extraction

Changed:

- Added `like_emoji_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO like_emojis` SQL and params in `_import_like_emojis` with
  helper-returned SQL and params.
- Added characterization coverage for helper SQL shape, parameter order, missing `likes_detail`
  skip, missing `emojis` skip, empty-list skip, missing `emoji_key` skip, default `likes_count=0`,
  and generated Beijing-time `created_at` format.

Behavior impact:

- Intended behavior change: none.
- `_import_like_emojis` still returns before any database call when `likes_detail` is absent or
  does not contain `emojis`.
- Empty `emojis` lists still produce no database writes.
- Individual emoji entries without a truthy `emoji_key` are still skipped.
- Valid emoji entries still upsert the same `like_emojis` fields using
  `ON CONFLICT(topic_id, emoji_key)`, preserving the existing `likes_count` default of `0`.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string
  generated inside the per-emoji branch.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 47 tests passed.
- Full backend unittest discovery: 650 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 user liked emoji insert statement helper extraction

Changed:

- Added `user_liked_emoji_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO user_liked_emojis` SQL and params in `_import_user_liked_emojis`
  with helper-returned SQL and params.
- Added characterization coverage for helper SQL shape, parameter order, missing `user_specific`
  skip, missing `liked_emojis` skip, empty-list skip, empty `emoji_key` skip, and
  `ON CONFLICT(topic_id, emoji_key) DO NOTHING` behavior.

Behavior impact:

- Intended behavior change: none.
- `_import_user_liked_emojis` still returns before any database call when `user_specific` is absent
  or does not contain `liked_emojis`.
- Empty `liked_emojis` lists still produce no database writes.
- Individual empty/falsy emoji keys are still skipped.
- Valid emoji keys still insert the same `user_liked_emojis` fields with
  `ON CONFLICT(topic_id, emoji_key) DO NOTHING`.
- No schema, config, compatibility, fallback, error handling, logging, commit order, timestamp, or
  public API semantics were changed.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 49 tests passed.
- Full backend unittest discovery: 652 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 comment insert statement helper extraction

Changed:

- Added `comment_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO comments` SQL and params in `_upsert_comment` with
  helper-returned SQL and params.
- Strengthened characterization coverage for missing `comment_id` skip, runtime group scope,
  owner/repliee IDs, parent comment ID, text/create-time fields, counter defaults, sticky default,
  generated Beijing-time `imported_at`, and full helper SQL/parameter order.

Behavior impact:

- Intended behavior change: none.
- `_upsert_comment` still returns before any database call when `comment_id` is missing/falsy.
- Runtime group resolution still happens in `_upsert_comment` after timestamp generation and before
  the write.
- Owner and repliee IDs still come from `owner.user_id` and `repliee.user_id`, defaulting to
  `None` when absent.
- Parent comment, text, create time, likes, rewards, replies, and sticky fields keep the same
  defaults and same `ON CONFLICT(comment_id) DO UPDATE SET` update list.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 50 tests passed.
- Full backend unittest discovery: 653 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 Q&A insert statement helper extraction

Changed:

- Added `question_insert_statement` and `answer_insert_statement` to
  `backend/storage/zsxq_database_helpers.py`, with compatibility wrappers in
  `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO questions` and `INSERT INTO answers` SQL and params in
  `_upsert_question` and `_upsert_answer` with helper-returned SQL and params.
- Added characterization coverage for anonymous question writes, missing-question skip,
  answer missing-owner skip, `owner_detail.estimated_join_time` fallback, Q&A defaults,
  generated Beijing-time `created_at`, and full helper SQL/parameter order.

Behavior impact:

- Intended behavior change: none.
- `_upsert_question` still skips only when both `owner.user_id` and question `text` are missing.
- Anonymous questions can still write with `owner_user_id=None` when text exists.
- `owner_detail.join_time` still has priority over `owner_detail.estimated_join_time`, which still
  falls back to an empty string when both are absent.
- Question defaults for `text`, `expired`, `anonymous`, `owner_questions_count`, `owner_status`, and
  `owner_location` are preserved.
- `_upsert_answer` still returns before any database call when `owner.user_id` is missing/falsy.
- Answer text still defaults to an empty string, and both Q&A writes keep the same
  `ON CONFLICT(topic_id) DO UPDATE SET` update lists.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 53 tests passed.
- Full backend unittest discovery: 656 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 article insert statement helper extraction

Changed:

- Added `article_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO articles` SQL and params in `_upsert_article` with
  helper-returned SQL and params.
- Added characterization coverage for article helper SQL shape, parameter order, URL defaults, and
  missing topic create-time fallback to an empty `created_at` string.

Behavior impact:

- Intended behavior change: none.
- `_upsert_article` still returns before any database call when both `title` and `article_id` are
  missing/falsy.
- `_upsert_article` still reads the topic create time with `SELECT create_time FROM topics WHERE
  topic_id = ?` before writing the article row.
- Missing topic create time still maps to `created_at=''`.
- `article_url` and `inline_article_url` still default to empty strings.
- The same `articles` fields and `ON CONFLICT(topic_id) DO UPDATE SET` update list are preserved.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 54 tests passed.
- Full backend unittest discovery: 657 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic file insert statement helper extraction

Changed:

- Added `topic_file_insert_statement` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced inline `INSERT INTO topic_files` SQL and params in `_import_files` with
  helper-returned SQL and params.
- Added characterization coverage for empty file-list skip, missing `file_id` skip, default
  file fields, generated Beijing-time `created_at`, and full helper SQL/parameter order.

Behavior impact:

- Intended behavior change: none.
- `_import_files` still returns before any database call when `files_data` is empty/falsy.
- Individual files without a truthy `file_id` are still skipped.
- Valid files still write the same `topic_files` fields with the same
  `ON CONFLICT(topic_id, file_id) DO UPDATE SET` update list.
- `name`, `hash`, `size`, `duration`, `download_count`, and `create_time` keep the same defaults.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800` string.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 56 tests passed.
- Full backend unittest discovery: 659 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic files backfill query helper extraction

Changed:

- Added `topic_files_backfill_query` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `SELECT` used by `backfill_topic_files_to_core_tables` with helper-returned
  SQL and params.
- Added characterization coverage for the existing backfill query shape before extraction, plus
  direct helper coverage for selected columns, joins, scoped params, empty-group legacy scope, and
  ordering.

Behavior impact:

- Intended behavior change: none.
- Backfill still scans `topic_files` joined with `topics` and `groups` using the same selected
  columns and `ORDER BY tf.topic_id ASC, tf.file_id ASC`.
- Group scoping still uses the existing `group_id_param` behavior, including `None` mapping to
  empty-string params for this legacy backfill path.
- Row unpacking, group upsert, file upsert, file-topic relation replacement, stats increments,
  batch commits, final commit, rollback-on-exception, and the compatibility method
  `backfill_topic_files_to_file_database` are unchanged.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original inline query.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 57 tests passed.
- Full backend unittest discovery: 660 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 database stats count query helper extraction

Changed:

- Added `database_stats_count_query` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline query-selection branches in `get_database_stats` with helper-returned SQL
  and params.
- Added characterization coverage for unscoped stats queries, group-scoped direct table queries,
  scoped `users` distinct-union query, topic-scoped child-table queries, and per-table exception
  fallback.
- Added direct helper coverage for unscoped, direct group scope, child-table scope, and scoped
  `users` query branches.

Behavior impact:

- Intended behavior change: none.
- `get_database_stats` still uses the same table list in the same order.
- Unscoped stats still execute `SELECT COUNT(*) FROM <table>` with no params.
- Group-scoped `groups`, `topics`, and `comments` still filter directly by `group_id`.
- Group-scoped `users` still uses the same `COUNT(DISTINCT user_id)` union over talks, comments,
  questions, questionees, and answers.
- Other group-scoped tables still filter by topics in the same group.
- Per-table exception handling still prints the same error prefix and returns `0` for that table
  while continuing the remaining tables.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original inline query branches.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 60 tests passed.
- Full backend unittest discovery: 663 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic hashtag extraction helper

Changed:

- Added `topic_tags_from_data` to `backend/storage/zsxq_database_helpers.py`, with a compatibility
  wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline text-source collection, hashtag regex matching, URL decoding, `#` stripping,
  and dedupe logic in `_import_tags` with the helper output.
- Added characterization coverage for missing-group skip, talk/question/answer/comment sources,
  URL-decoded names, duplicate hashtags, empty decoded names, and link behavior when `_upsert_tag`
  returns no tag ID.

Behavior impact:

- Intended behavior change: none.
- `_import_tags` still returns before tag extraction when `topic_data.group.group_id` is missing.
- The helper still reads hashtag markup from talk text, question text, answer text, and
  `show_comments[*].text`.
- Hashtag titles are still URL-decoded, leading/trailing `#` characters are stripped, empty names
  are skipped, and duplicates collapse through set semantics.
- Decode failures still print the same `解码标签失败:` prefix.
- `_import_tags` still calls `_upsert_tag(group_id, tag_name, hid)` and links only when a truthy
  tag ID is returned.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public API
  semantics were changed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization run passed against the original inline `_import_tags` implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 62 tests passed.
- Full backend unittest discovery: 665 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 Beijing timestamp helper extraction

Changed:

- Added `beijing_now_timestamp` to `backend/storage/zsxq_database_helpers.py`, with a
  compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced 15 repeated East-8 timestamp generation blocks in
  `backend/storage/zsxq_database.py` with `_beijing_now_timestamp()`.
- Added direct helper coverage for the existing `YYYY-MM-DDTHH:MM:SS.mmm+0800` timestamp
  format.

Behavior impact:

- Intended behavior change: none.
- Every replaced call site still obtains the current timestamp at the same point in its method
  or loop.
- Timestamp formatting remains the existing Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800`
  string.
- Existing created_at/imported_at call sites, skip paths, insert/update SQL, parameter order,
  commit/rollback behavior, fallback behavior, and public API semantics are unchanged.
- No schema, config, compatibility, fallback, error handling, logging, commit order, or public
  API semantics were changed.

Verification:

```powershell
rg -n "from datetime import datetime, timezone, timedelta|datetime\.now\(|strftime\('%Y-%m-%dT%H:%M:%S.%f'\)\[:-3\] \+ '\+0800'" backend\storage\zsxq_database.py
rg -n "_beijing_now_timestamp|current_time = _beijing_now_timestamp" backend\storage\zsxq_database.py
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Inline timestamp-generation scan found no remaining matches in
  `backend/storage/zsxq_database.py`.
- Helper call-site scan found the wrapper plus 15 timestamp call sites.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 63 tests passed.
- Full backend unittest discovery: 666 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic user payload iterator extraction

Changed:

- Added `iter_topic_user_payloads_from_data` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `_import_all_users` source traversal with iteration over the helper.
- Added direct helper coverage for talk owner, non-anonymous question owner, questionee,
  answer owner, latest-like owners, comment owners, and repliees.
- Added characterization coverage for `_import_all_users` call order, including anonymous
  question owner skip and empty like-owner pass-through.

Behavior impact:

- Intended behavior change: none.
- `_import_all_users` still calls `_upsert_user` in the existing source order.
- The helper is an iterator so `_upsert_user` calls still happen as each source is reached;
  malformed later payload sections do not move ahead of earlier side effects.
- Anonymous question owners are still skipped, while questionees are still imported.
- Empty owner payloads under `latest_likes` are still passed through to `_upsert_user`, where
  existing skip behavior is preserved.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_all_users_preserves_existing_source_order -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline `_import_all_users`
  implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 65 tests passed.
- Full backend unittest discovery: 668 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 topic image payload collection helper

Changed:

- Added `topic_image_payloads_from_data` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `_import_images` talk/comment image collection with the helper output.
- Added direct helper coverage for talk images, comment images, missing `comment_id`, and empty
  comment payloads.
- Added characterization coverage for `_import_images` `_upsert_image` call order.

Behavior impact:

- Intended behavior change: none.
- `_import_images` still imports talk images before comment images.
- Comment images still carry their existing `comment_id`; missing `comment_id` still passes
  `None`.
- The helper returns a fully collected list rather than yielding lazily, preserving the original
  behavior where image writes begin only after source collection succeeds.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, timestamp generation, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_images_preserves_existing_collection_order -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline `_import_images`
  implementation.
- `py_compile` passed.
- `tests.test_zsxq_database_helpers`: 67 tests passed.
- Full backend unittest discovery: 670 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 like emoji iterator helper

Changed:

- Added `iter_valid_like_emoji_payloads` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `_import_like_emojis` missing/empty `emoji_key` filtering with the
  helper output.
- Added direct helper coverage for missing `emoji_key`, empty `emoji_key`, and valid emoji
  payload ordering.

Behavior impact:

- Intended behavior change: none.
- `_import_like_emojis` still returns before processing when `likes_detail` or `emojis` is
  missing.
- `emoji_key` filtering still skips missing or empty keys and preserves the order of valid
  emoji payloads.
- The helper is lazy, so timestamp generation and SQL execution still occur only when a valid
  emoji payload is reached.
- The existing no-op non-empty `emojis` branch remains in the class method to preserve the
  original control-flow shape.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_like_emojis_preserves_skip_defaults_and_upsert_params -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_iter_valid_like_emoji_payloads_filters_missing_keys tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_like_emojis_preserves_skip_defaults_and_upsert_params -v
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline `_import_like_emojis`
  implementation.
- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_database_helpers`: 68 tests passed.
- Full backend unittest discovery: 671 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 user liked emoji key iterator helper

Changed:

- Added `iter_valid_user_liked_emoji_keys` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `_import_user_liked_emojis` falsey-key filtering with the helper output.
- Added direct helper coverage for empty string, `None`, `False`, and valid emoji key ordering.

Behavior impact:

- Intended behavior change: none.
- `_import_user_liked_emojis` still returns before processing when `user_specific` or
  `liked_emojis` is missing.
- Falsey liked emoji keys are still skipped and valid keys keep their original order.
- The helper is lazy, so SQL execution still occurs only when a valid key is reached.
- The existing no-op non-empty `liked_emojis` branch remains in the class method to preserve the
  original control-flow shape.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_user_liked_emojis_preserves_skip_and_insert_params -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_iter_valid_user_liked_emoji_keys_filters_falsey_keys tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_user_liked_emojis_preserves_skip_and_insert_params -v
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline
  `_import_user_liked_emojis` implementation.
- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_database_helpers`: 69 tests passed.
- Full backend unittest discovery: 672 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 latest like iterator helper

Changed:

- Added `iter_valid_latest_like_payloads` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `_import_likes` owner/user ID filtering with the helper output.
- Added direct helper coverage for missing owner, missing user ID, falsey user ID, and valid
  like payload ordering.

Behavior impact:

- Intended behavior change: none.
- `_import_likes` still returns before processing when `latest_likes` is missing.
- The `latest_likes` delete statement still runs before any per-like insert when the key is
  present, including an empty list.
- Likes with missing or falsey `owner.user_id` are still skipped, and valid likes keep their
  original order.
- The helper is lazy, so timestamp generation and both `likes`/`latest_likes` SQL writes still
  occur only when a valid like payload is reached.
- The existing no-op non-empty `latest_likes` branch remains in the class method to preserve the
  original control-flow shape.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_likes_preserves_delete_skip_and_insert_order -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_iter_valid_latest_like_payloads_filters_missing_user_ids tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_likes_preserves_delete_skip_and_insert_order -v
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline `_import_likes`
  implementation.
- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_database_helpers`: 70 tests passed.
- Full backend unittest discovery: 673 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 comment image iterator helper

Changed:

- Added `iter_valid_comment_image_payloads` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline `_import_comment_images` falsey `image_id` filtering with the helper output.
- Added direct helper coverage for empty payloads, falsey image IDs, and valid comment-image
  payload ordering.

Behavior impact:

- Intended behavior change: none.
- `_import_comment_images` still skips images with missing or falsey `image_id`.
- Valid comment images keep their original order.
- The helper is lazy, so timestamp generation and SQL execution still occur only when a valid
  image payload is reached.
- Comment image writes still use `_image_insert_statement` with `missing_numeric_default=0`.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_image_writes_preserve_skip_paths_and_distinct_numeric_defaults -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_iter_valid_comment_image_payloads_filters_missing_image_ids tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_image_writes_preserve_skip_paths_and_distinct_numeric_defaults -v
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline `_import_comment_images`
  implementation.
- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_database_helpers`: 71 tests passed.
- Full backend unittest discovery: 674 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 comment image batch helper

Changed:

- Added `comment_image_batch_from_comment` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Reused the helper from both `_import_comments` and `import_additional_comments`.
- Added direct helper coverage for missing images, empty images, valid image batches, and the
  existing missing-`comment_id` `KeyError` behavior when `images` is non-empty.
- Added `_import_comments` characterization coverage for upsert-before-image-import ordering and
  missing-`comment_id` behavior.

Behavior impact:

- Intended behavior change: none.
- Comments are still upserted before their image batches are considered.
- Comments without `images` or with empty `images` still do not trigger comment-image import.
- Comments with non-empty `images` still read `comment['comment_id']`, preserving the existing
  `KeyError` behavior if the key is missing.
- `import_additional_comments` still upserts owner/repliee users before comment upsert, then
  imports comment images.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_comment_image_batch_from_comment_preserves_existing_access_semantics tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_comments_preserves_upsert_and_image_import_order tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_image_writes_preserve_skip_paths_and_distinct_numeric_defaults -v
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_database_helpers`: 73 tests passed.
- Full backend unittest discovery: 676 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 additional comment user iterator helper

Changed:

- Added `iter_additional_comment_user_payloads` to `backend/storage/zsxq_database_helpers.py`,
  with a compatibility wrapper in `backend/storage/zsxq_database.py`.
- Replaced the inline owner/repliee user-upsert checks in `import_additional_comments` with the
  helper output.
- Added direct helper coverage for missing users, falsey owner/repliee values, and owner-before-
  repliee ordering.
- Added `import_additional_comments` characterization coverage for empty-list early return, print
  behavior, user upsert order, comment upsert order, and image import order.

Behavior impact:

- Intended behavior change: none.
- `import_additional_comments` still returns before printing or writing when `comments` is empty.
- Truthy `owner` and `repliee` payloads are still upserted before the comment itself, in owner then
  repliee order.
- Falsey `owner` and `repliee` payloads are still skipped.
- Comment upsert still happens before comment-image import for each comment.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit/rollback
  behavior, and public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_additional_comments_preserves_user_comment_image_order -v
uv run python -m py_compile backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_iter_additional_comment_user_payloads_preserves_truthy_owner_repliee_order tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_additional_comments_preserves_user_comment_image_order -v
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline
  `import_additional_comments` implementation.
- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_database_helpers`: 75 tests passed.
- Full backend unittest discovery: 678 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage/helper code.

### 2026-06-12 - P2 import no-op branch cleanup

Changed:

- Removed four `if ...: pass` branches from `_import_likes`, `_import_like_emojis`,
  `_import_user_liked_emojis`, and `_import_comments`.
- Confirmed no remaining `pass  # 数据已导入，无需额外日志` / `无需额外日志` placeholders in
  `backend/storage/zsxq_database.py`.

Behavior impact:

- Intended behavior change: none.
- These branches only executed `pass` and had no logging, return value, SQL, timestamp, commit,
  rollback, or exception side effects.
- Existing early returns, delete statements, per-item filtering, SQL write order, timestamp
  generation, and comment-image import behavior are unchanged.
- No legacy, fallback, compatibility, schema, config, logging, or public API semantics were
  removed.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_likes_preserves_delete_skip_and_insert_order tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_like_emojis_preserves_skip_defaults_and_upsert_params tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_user_liked_emojis_preserves_skip_and_insert_params tests.test_zsxq_database_helpers.ZSXQDatabaseHelperTests.test_import_comments_preserves_upsert_and_image_import_order -v
uv run python -m py_compile backend\storage\zsxq_database.py
rg -n "pass\s*# 数据已导入|无需额外日志" backend\storage\zsxq_database.py backend\storage\zsxq_database_helpers.py tests\test_zsxq_database_helpers.py
uv run python -m unittest tests.test_zsxq_database_helpers -v
uv run python -m unittest discover -s tests
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-cleanup characterization tests passed against the original no-op-branch implementation.
- `py_compile` passed.
- Focused post-cleanup tests passed.
- Residual no-op placeholder search returned no matches.
- `tests.test_zsxq_database_helpers`: 75 tests passed.
- Full backend unittest discovery: 678 tests passed, 15 skipped.
- PostgreSQL compatibility debt scan: no SQLite compatibility patterns found.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.
- Frontend build is not planned because this slice only changes backend storage code and docs.

### 2026-06-12 - P3 column comment import iterator helper

Changed:

- Added characterization coverage for `ZSXQColumnsDatabase.import_comments` empty-list early return,
  parent-before-reply insert order, `parent_comment_id` in-place mutation for nested replies, existing
  parent preservation, returned count, and commit behavior.
- Added `_iter_topic_comment_import_payloads` to `backend/storage/zsxq_columns_database_helpers.py`.
- Reused the helper from `ZSXQColumnsDatabase.import_comments` so the class method now keeps only
  insert/count/commit orchestration.

Behavior impact:

- Intended behavior change: none.
- Empty comments still return `0` without writes or commit.
- Main comments are still inserted before their nested replies.
- Replies missing `parent_comment_id` are still mutated in place with the parent `comment_id`; replies
  with an existing parent keep that value.
- Return count and commit timing are unchanged.
- Existing SQL, schema, config, fallback behavior, error handling, logging, and public API semantics
  are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_import_comments_preserves_order_parent_mutation_and_commit -v
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_iter_topic_comment_import_payloads_preserves_order_and_parent_mutation tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_import_comments_preserves_order_parent_mutation_and_commit -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization test passed against the original inline `import_comments`
  implementation.
- `py_compile` passed.
- Focused helper/import tests passed.
- `tests.test_zsxq_columns_database_helpers`: 64 tests passed.
- Full backend unittest discovery: 680 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P3 column topic related payload iterator helper

Changed:

- Added `_iter_topic_related_payloads` to `backend/storage/zsxq_columns_database_helpers.py`.
- Reused the helper from `ZSXQColumnsDatabase._insert_topic_related_payloads`, leaving the class
  method responsible only for dispatching to the existing `_insert_image`, `_insert_file`,
  `_insert_video`, and `_insert_comment` methods.
- Added direct helper coverage for empty input, image/file/content-voice/video/comment ordering,
  and falsey content-voice/video skip behavior.

Behavior impact:

- Intended behavior change: none.
- Topic images are still inserted before talk files, then `content_voice`, then video, then
  `show_comments`.
- Empty/missing related payloads are still skipped.
- The existing class method still calls the same `_insert_*` methods with the same `topic_id` and
  payload objects.
- Existing SQL, schema, config, fallback behavior, error handling, logging, commit timing, and
  public API semantics are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_topic_related_payloads_preserves_order_and_empty_skip_behavior -v
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_iter_topic_related_payloads_preserves_existing_order tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_topic_related_payloads_preserves_order_and_empty_skip_behavior tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_topic_detail_preserves_related_insert_order -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor class-method characterization test passed against the original inline related-payload
  traversal.
- `py_compile` passed.
- Focused helper/class/import tests passed.
- `tests.test_zsxq_columns_database_helpers`: 65 tests passed.
- Full backend unittest discovery: 681 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P3 column comment user iterator helper

Changed:

- Added characterization coverage for `ZSXQColumnsDatabase._insert_comment` owner/repliee user-upsert
  order, falsey owner/repliee skip behavior, group-resolution order, and final SQL parameters.
- Added `_iter_topic_comment_user_payloads` to
  `backend/storage/zsxq_columns_database_helpers.py`.
- Reused the helper from `_insert_comment`, keeping the method responsible for `insert_user`
  execution, group resolution, and the existing comment upsert statement.

Behavior impact:

- Intended behavior change: none.
- Comment owner is still upserted before repliee when both are truthy.
- Falsey owner/repliee payloads are still skipped and produce `None` user IDs.
- Group scope is still resolved after user handling and before the comment insert.
- Comment insert SQL, parameter order, missing-ID early return, fallback group resolution,
  schema/config semantics, logging, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_comment_writes_group_id_from_runtime_scope -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_comment_preserves_user_upsert_order_and_falsey_skip -v
uv run python -m py_compile backend\storage\zsxq_columns_database.py backend\storage\zsxq_columns_database_helpers.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_iter_topic_comment_user_payloads_preserves_owner_repliee_order tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_comment_preserves_user_upsert_order_and_falsey_skip tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_insert_comment_writes_group_id_from_runtime_scope -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor characterization tests passed against the original inline `_insert_comment`
  implementation.
- `py_compile` passed.
- Focused helper/class tests passed.
- `tests.test_zsxq_columns_database_helpers`: 67 tests passed.
- Full backend unittest discovery: 683 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P3 column comment image loader extraction

Changed:

- Added `_load_topic_comment_images` to `backend/storage/zsxq_columns_database.py`.
- Reused the method from `ZSXQColumnsDatabase.get_topic_comments`, leaving the outer method
  responsible for comment query execution, optional `images` attachment, and nesting.
- Added direct characterization coverage for comment-image query parameters, row mapping shape, and
  empty image results.

Behavior impact:

- Intended behavior change: none.
- `get_topic_comments` still queries base comments first and then queries images once per comment in
  comment order.
- Comments with images still receive an `images` field; comments without images still omit that
  field.
- Nested comment shape, scoped image-query parameters, row mapping, SQL, fallback behavior, schema
  semantics, config semantics, logging, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_topic_comments_preserve_comment_image_queries_and_nested_shape -v
uv run python -m py_compile backend\storage\zsxq_columns_database.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_load_topic_comment_images_preserves_query_params_and_shape tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_topic_comments_preserve_comment_image_queries_and_nested_shape -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor `get_topic_comments` characterization test passed against the original inline
  comment-image loading implementation.
- `py_compile` passed.
- Focused image-loader/comment tests passed.
- `tests.test_zsxq_columns_database_helpers`: 68 tests passed.
- Full backend unittest discovery: 684 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P3 column pending queue executor extraction

Changed:

- Added characterization coverage for `get_pending_videos`, `get_pending_files`, and
  `get_uncached_images`, including scoped execute arity, unscoped execute arity, and returned row
  shapes.
- Added `ZSXQColumnsDatabase._fetch_optional_params_rows`.
- Reused the helper from the three pending/cache queue readers to remove repeated optional-param
  execute/fetchall branches.

Behavior impact:

- Intended behavior change: none.
- Scoped queue queries still call `execute(sql, params)` with the same parameter tuple.
- Unscoped queue queries still call `execute(sql)` without passing `None` as a params argument.
- Pending video, pending file, and uncached image row shapes are preserved.
- Existing SQL, schema, config, fallback behavior, logging, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_pending_queue_methods_preserve_execute_arity_and_row_shapes -v
uv run python -m py_compile backend\storage\zsxq_columns_database.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_pending_queue_methods_preserve_execute_arity_and_row_shapes tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_pending_queue_queries_preserve_group_filter_branches tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_pending_queue_queries_preserve_unscoped_branches -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor pending/cache queue method characterization test passed against the original inline
  execute/fetchall branches.
- `py_compile` passed.
- Focused pending queue tests passed.
- `tests.test_zsxq_columns_database_helpers`: 69 tests passed.
- Full backend unittest discovery: 685 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P3 column group topic id loader extraction

Changed:

- Added `ZSXQColumnsDatabase._fetch_group_topic_ids`.
- Reused the helper from `get_existing_topic_ids` and `clear_all_data`.
- Added direct helper coverage for query parameters, list ordering, and empty-list shape.

Behavior impact:

- Intended behavior change: none.
- `get_existing_topic_ids` still returns a `set` of topic IDs.
- `clear_all_data` still uses the fetched topic IDs as an ordered list for child-delete parameter
  binding before group-level deletes.
- Delete order, stats updates, commit/rollback behavior, print behavior, SQL, schema, config,
  fallback behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_incremental_select_methods_preserve_execute_params_and_fetch_shape tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_clear_all_data_preserves_delete_order_stats_and_commit -v
uv run python -m py_compile backend\storage\zsxq_columns_database.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_fetch_group_topic_ids_preserves_query_params_order_and_empty_shape tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_incremental_select_methods_preserve_execute_params_and_fetch_shape tests.test_zsxq_columns_database_helpers.ZSXQColumnsDatabaseHelperTests.test_clear_all_data_preserves_delete_order_stats_and_commit -v
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor incremental-select and clear-data characterization tests passed against the original
  duplicated group-topic-ID query implementation.
- `py_compile` passed.
- Focused helper/incremental/clear-data tests passed.
- `tests.test_zsxq_columns_database_helpers`: 70 tests passed.
- Full backend unittest discovery: 686 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader target path helper

Changed:

- Added characterization coverage for `ZSXQFileDownloader.download_file` local target-path behavior
  when the source filename contains characters filtered by the existing safe-filename rule.
- Added `download_target_path` to `backend/crawlers/zsxq_file_downloader_helpers.py`.
- Reused the helper from `ZSXQFileDownloader.download_file` for initial safe filename and local
  target path construction.

Behavior impact:

- Intended behavior change: none.
- The safe filename rule is unchanged and still allows alphanumeric characters plus
  `._-（）()[]{}`.
- The fallback filename for fully filtered names remains `file_{file_id}`.
- Content-Disposition filename override behavior remains separate and unchanged.
- Existing retry behavior, signed URL handling, partial-file cleanup, stop handling, download status
  updates, SQL/storage side effects, config semantics, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_safe_filename_for_local_target -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderFileDataHelperTests.test_download_target_path_reuses_safe_filename_contract tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_safe_filename_for_local_target tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_content_disposition_for_default_filename -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
uv run python scripts\scan_postgres_compat_debt.py
git diff --check
```

Result:

- Pre-refactor safe-target-path characterization test passed against the original inline filename
  and path construction.
- `py_compile` passed.
- Focused target-path and content-disposition tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 46 tests passed.
- Full backend unittest discovery: 688 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader body write helper

Changed:

- Added characterization coverage for chunked response body writes, empty chunk skipping, progress
  logging, body-phase stop handling, and size-mismatch retry preservation.
- Added `ZSXQFileDownloader._write_download_response_body`.
- Reused the helper from `ZSXQFileDownloader.download_file` to separate response-body writes from
  retry/orchestration logic.

Behavior impact:

- Intended behavior change: none.
- Chunk write order, empty chunk skip behavior, progress log timing, stop check timing,
  `_handle_download_stop` side effects, size-mismatch validation after body write, retry loop,
  final status updates, signed URL handling, schema/config/API behavior, and public API behavior are
  unchanged.
- The stop-path tests mock `remove_partial_download` where needed to avoid platform file-lock
  differences while preserving the current call/status semantics; this slice does not fix or change
  stop-time partial-file deletion behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_preserves_progress_for_chunked_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_stops_during_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_accepts_raw_file_id_payload -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_write_download_response_body_preserves_progress_stop_and_empty_chunks tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_preserves_progress_for_chunked_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_stops_during_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_accepts_raw_file_id_payload -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor body-write characterization tests passed against the original inline body loop.
- `py_compile` passed.
- Focused body-write/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 49 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 691 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader existing-file skip helper

Changed:

- Added characterization coverage for `ZSXQFileDownloader.download_file` local-file short-circuit
  behavior when the target file already exists and size matches.
- Added characterization coverage for the existing-file size-mismatch branch continuing into a
  fresh download and replacing the local file.
- Added `ZSXQFileDownloader._skip_existing_download_if_complete` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- Existing matching local files still return `"skipped"` before any signed-URL request and still
  update download status to `completed` with the existing path.
- Existing size-mismatched local files still log the mismatch and continue through the normal
  signed-URL, response handling, body write, size verification, replace, status-update, and interval
  flow.
- Retry behavior, content-disposition filename override, partial-file cleanup, stop handling,
  final failure status, schema/config/API behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_skips_existing_matching_file_without_request tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_redownloads_existing_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_safe_filename_for_local_target tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor existing-file characterization tests passed against the original inline branch.
- `py_compile` passed.
- Focused existing-file/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 51 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 693 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader success finalizer helper

Changed:

- Added characterization coverage for successful `download_file` finalization, including final file
  replacement, `.part` removal, completed status update, success logs, counter increments, and
  interval-callback ordering.
- Added direct helper coverage for the same side effects starting from an existing `.part` file.
- Added `ZSXQFileDownloader._complete_successful_download` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Successful downloads still replace the `.part` file with the final file before logging completion
  and updating file status.
- `download_count` and `current_batch_count` are still incremented before download-interval handling.
- Retry behavior, size-mismatch handling, content-disposition filename override, stop handling,
  partial-file cleanup, final failure status, schema/config/API behavior, and public API behavior are
  unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_preserves_progress_for_chunked_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_accepts_raw_file_id_payload tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_complete_successful_download_preserves_side_effect_order tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_preserves_progress_for_chunked_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_accepts_raw_file_id_payload tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor success-finalization characterization tests passed against the original inline
  success branch.
- `py_compile` passed.
- Focused success-finalizer/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 53 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 695 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader final failure helper

Changed:

- Added characterization coverage for repeated HTTP download failures reaching the final
  after-retries failure path.
- Added direct helper coverage for explicit last-error details and default final-failure details.
- Added `ZSXQFileDownloader._mark_download_failed_after_retries` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- Repeated HTTP failures still attempt the configured three downloads and preserve the final
  `http_status` / `HTTP 500` status update.
- Missing last-error details still fall back to `download_failed` / `文件下载失败`.
- Download URL early failure, retry sleep behavior, size-mismatch retry behavior, exception partial
  cleanup, stop handling, schema/config/API behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_when_download_url_missing -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_mark_download_failed_after_retries_preserves_error_detail_defaults tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_when_download_url_missing -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor final-failure characterization tests passed against the original inline final
  failure branch.
- `py_compile` passed.
- Focused final-failure/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 55 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 697 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader URL unavailable helper

Changed:

- Added characterization coverage for missing download URL failures preserving default
  `download_url_unavailable` status details.
- Added characterization coverage for API-provided download URL error details such as
  `1030` / `mobile only` flowing into the failed file status update.
- Added direct helper coverage for default and API error detail mapping.
- Added `ZSXQFileDownloader._mark_download_url_unavailable` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- Missing download URLs still log `"   ❌ 无法获取下载链接"`, update file status to `failed`,
  and return `False` before any download `session.get`.
- `last_download_url_error` still flows through `download_url_failure_detail`; the default
  fallback remains `download_url_unavailable` / `无法获取下载链接`.
- Retry loop behavior, HTTP/body failures, size mismatch handling, partial cleanup, stop
  handling, schema/config/API behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_when_download_url_missing tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_with_download_url_api_error_detail tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_mark_download_url_unavailable_preserves_default_and_api_error_details tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_when_download_url_missing tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_with_download_url_api_error_detail tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor download URL failure characterization tests passed against the original inline
  early-failure branch.
- `py_compile` passed.
- Focused URL-unavailable/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 57 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 699 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader size mismatch helper

Changed:

- Added characterization coverage for a size-mismatched body download being deleted and then
  retried successfully on the next response.
- Added direct helper coverage for mismatch cleanup and matching-size no-op behavior.
- Added `ZSXQFileDownloader._handle_download_size_mismatch` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- Size mismatch still logs `"   ⚠️ 文件大小不匹配: ..."` and deletes the `.part` file before
  continuing the retry loop.
- Matching file size still leaves the `.part` file in place for normal success finalization.
- Repeated size mismatches still exhaust the configured retry count and preserve the final
  `size_mismatch` failure status.
- Download URL failures, HTTP/body failures, stop handling, success finalization, partial cleanup
  in exception paths, schema/config/API behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_after_size_mismatch_before_success tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_handle_download_size_mismatch_preserves_cleanup_and_noop_paths tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_after_size_mismatch_before_success tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor size-mismatch retry characterization tests passed against the original inline
  mismatch branch.
- `py_compile` passed.
- Focused size-mismatch/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 59 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 701 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader response filename override helper

Changed:

- Added characterization coverage that a named file ignores `Content-Disposition` filename
  overrides and keeps its original target path.
- Added direct helper coverage for response filename override and no-op paths.
- Added `ZSXQFileDownloader._apply_response_filename_override` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- Default `file_...` names still use `Content-Disposition` filename when present and parsable.
- Existing real file names still ignore `Content-Disposition` and keep their original target path.
- The override branch still logs `"   📝 从响应头获取到真实文件名: ..."` only when an override is
  actually applied.
- Download URL failures, HTTP/body failures, size mismatch handling, partial cleanup, stop
  handling, success finalization, schema/config/API behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_content_disposition_for_default_filename tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_keeps_named_file_despite_content_disposition tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_apply_response_filename_override_preserves_override_and_noop_paths tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_content_disposition_for_default_filename tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_keeps_named_file_despite_content_disposition tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor filename override characterization tests passed against the original inline
  response-header branch.
- `py_compile` passed.
- Focused response-filename/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 61 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 703 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader HTTP failure helper

Changed:

- Added characterization coverage for HTTP 404 body-download failures preserving the current
  retry-until-final-failure behavior.
- Added direct helper coverage for HTTP failure detail and log mapping.
- Added `ZSXQFileDownloader._record_download_http_failure` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Non-200 HTTP responses still record `http_status` / `HTTP <status>` details and log
  `"   ❌ 下载失败: HTTP <status>"`.
- HTTP 404 responses still follow the existing body-download retry loop and ultimately preserve
  the final failed status update after all attempts are exhausted.
- Download URL failures, response filename override, body write, size mismatch handling, partial
  cleanup, stop handling, success finalization, schema/config/API behavior, and public API
  behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_marks_final_failure_after_http_404 tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_record_download_http_failure_preserves_error_detail_and_log tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_marks_final_failure_after_http_404 tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor HTTP failure characterization tests passed against the original inline branch.
- `py_compile` passed.
- Focused HTTP-failure/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 63 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 705 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader exception cleanup helper

Changed:

- Added characterization coverage for body-stream exceptions preserving retry, partial-file
  cleanup, and final `download_exception` status details.
- Added direct helper coverage for exception detail/log mapping with and without a `.part` file.
- Added `ZSXQFileDownloader._record_download_exception` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Body download exceptions still retry three times, record `download_exception` / exception text,
  log `"   ❌ 下载异常: <error>"`, and delete the partial `.part` file when present.
- Final after-retries failure still writes the last exception detail to file status and logs
  `"   🚫 文件下载重试3次仍失败: <error>"`.
- Download URL failures, HTTP failures, response filename override, body progress/stop handling,
  size mismatch handling, success finalization, schema/config/API behavior, and public API behavior
  are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_cleans_partial_file_after_body_exception_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_marks_final_failure_after_http_404 -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_record_download_exception_preserves_error_detail_log_and_cleanup tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_cleans_partial_file_after_body_exception_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_marks_final_failure_after_http_404 tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor exception cleanup characterization tests passed against the original inline branch.
- `py_compile` passed.
- Focused exception-cleanup/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 65 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 707 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader retry wait helper

Changed:

- Added characterization coverage that a retrying body download still logs the retry wait message
  and sleeps for the existing computed delay.
- Added direct helper coverage for retry wait log and delay mapping.
- Added `ZSXQFileDownloader._wait_before_download_retry` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Retry attempts still use `download_retry_wait(attempt, download_retries)`, so attempt 1 still
  logs `"   🔄 文件下载重试 2/3，等待 2 秒..."` and sleeps for 2 seconds.
- The retry wait still occurs after the previous failure log and before the next signed-URL lookup.
- Download URL failures, HTTP/body exceptions, response filename override, body progress/stop
  handling, size mismatch handling, success finalization, schema/config/API behavior, and public
  API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_preserves_retry_wait_log_and_delay tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_wait_before_download_retry_preserves_log_and_delay tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_preserves_retry_wait_log_and_delay tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor retry-wait characterization tests passed against the original inline branch.
- `py_compile` passed.
- Focused retry-wait/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 67 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 709 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader response request helper

Changed:

- Added characterization coverage that `download_file` still requests the signed download URL
  with `timeout=300` and `stream=True`, and still logs the start-download message.
- Added direct helper coverage for response request log, return value, and `session.get` arguments.
- Added `ZSXQFileDownloader._request_download_response` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Download requests still log `"   🚀 开始下载..."` before calling `session.get`.
- Signed download URLs are still requested with `timeout=300` and `stream=True`.
- The response object still flows unchanged into filename override, HTTP status handling, body
  writing, size mismatch handling, and success/failure finalization.
- Download URL failures, retry wait behavior, HTTP/body exceptions, response filename override,
  body progress/stop handling, size mismatch handling, success finalization, schema/config/API
  behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_requests_response_with_stream_timeout_and_log tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_request_download_response_preserves_stream_timeout_and_log tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_requests_response_with_stream_timeout_and_log tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_body_download_once tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor response-request characterization tests passed against the original inline branch.
- `py_compile` passed.
- Focused response-request/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 69 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 711 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader body target helper

Changed:

- Added characterization coverage that a stale `.part` file is cleared before a successful
  body write.
- Added direct helper coverage for total size, expected size, `.part` path, and cleanup
  behavior.
- Added `ZSXQFileDownloader._prepare_download_body_target` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Successful HTTP 200 downloads still derive `total_size` from `Content-Length`, derive
  `expected_size` from file metadata when positive or from `Content-Length` when missing,
  and use `<file_path>.part`.
- Existing `.part` files are still removed before body writing begins.
- Body progress/stop handling, size mismatch handling, success finalization, retry wait,
  response request, HTTP/body exceptions, schema/config/API behavior, and public API behavior
  are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_clears_existing_partial_file_before_successful_body_write tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_requests_response_with_stream_timeout_and_log -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_prepare_download_body_target_preserves_sizes_temp_path_and_cleanup tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_clears_existing_partial_file_before_successful_body_write tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_requests_response_with_stream_timeout_and_log tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor body-target characterization tests passed against the original inline branch.
- `py_compile` passed.
- Focused body-target/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 71 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 713 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader file target helper

Changed:

- Added characterization coverage that a file payload without `file_id` logs the current
  preparation messages, returns `False`, does not request a signed URL, and does not update
  download status.
- Added direct helper coverage for file metadata logging, safe target path generation,
  missing-`file_id` early return, and stop-check early return.
- Added `ZSXQFileDownloader._prepare_download_file_target` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- `download_file` still logs the file name, byte size, MB display, and download count before
  checking `file_id`.
- Missing `file_id` still returns `False` before stop checks, signed URL requests, local target
  checks, or database status updates.
- A stopped task still returns `False` before target path generation, existing-file checks,
  signed URL requests, or database status updates.
- Normal downloads still use `download_target_path(self.download_dir, file_name, file_id)`, keep
  the original `file_name` for later response-header override handling, and preserve existing
  skip, retry, request, body-write, size-mismatch, success, failure, schema/config/API, and public
  API behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_without_file_id_logs_and_returns_before_request -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_prepare_download_file_target_preserves_logs_target_and_early_returns tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_without_file_id_logs_and_returns_before_request tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_uses_safe_filename_for_local_target tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_accepts_raw_file_id_payload -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor missing-`file_id` characterization test passed against the original inline branch.
- `py_compile` passed.
- Focused file-target/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 73 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 715 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader signed URL helper

Changed:

- Re-ran existing characterization coverage for missing signed download URLs before the
  production extraction.
- Added direct helper coverage for successful signed URL return, no-op status/log behavior on
  success, and unavailable URL status/log behavior using `last_download_url_error`.
- Added `ZSXQFileDownloader._get_download_url_or_mark_unavailable` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- `download_file` still calls the existing `get_download_url(file_id)` before requesting the
  response body.
- Empty or missing signed URLs still log `"   ❌ 无法获取下载链接"`, update download status to
  `failed`, preserve API error details from `last_download_url_error`, and return `False` before
  `session.get`.
- Successful signed URL lookup still performs no status update or extra log before the existing
  response request helper runs.
- Retry wait, HTTP request options, response filename override, body writing, size mismatch,
  partial-file cleanup, success finalization, schema/config/API behavior, and public API behavior
  are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_when_download_url_missing tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_with_download_url_api_error_detail -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_get_download_url_or_mark_unavailable_preserves_success_and_failure_paths tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_when_download_url_missing tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_failed_with_download_url_api_error_detail tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_accepts_raw_file_id_payload -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor missing signed URL characterization tests passed against the original inline
  branch.
- `py_compile` passed.
- Focused signed URL/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 74 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 716 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader successful response helper

Changed:

- Re-ran existing characterization coverage for successful completion, stop-during-body, and
  repeated size-mismatch behavior before the production extraction.
- Added direct helper coverage for HTTP 200 response handling across completion, retryable
  size mismatch, and stopped body-write paths.
- Added `ZSXQFileDownloader._handle_successful_download_response` and reused it from
  `download_file`.

Behavior impact:

- Intended behavior change: none.
- HTTP 200 responses still prepare the same `Content-Length`/expected-size/`.part` target before
  body writing.
- Body writing still preserves progress logging, stop checks, and stop status updates.
- Size mismatch still logs the same warning, removes the `.part` file, returns the same
  `size_mismatch` detail to the outer retry loop, and retries until the existing retry limit.
- Successful body writes still replace the final file, log completion and path, update status to
  `completed`, increment counters, and apply existing interval behavior.
- Signed URL lookup, response request, response filename override, HTTP failure handling,
  exception cleanup, final failure handling, schema/config/API behavior, and public API behavior
  are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_stops_during_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_handle_successful_download_response_preserves_completion_retry_and_stop_paths tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_stops_during_body_download tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_retries_and_fails_on_size_mismatch -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor HTTP 200 response characterization tests passed against the original inline
  branch.
- `py_compile` passed.
- Focused successful-response/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 75 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 717 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader response dispatch helper

Changed:

- Added characterization coverage that a non-200 response with `Content-Disposition` still applies
  the response filename override before recording the HTTP failure.
- Added direct helper coverage for response dispatch across non-200 filename override plus HTTP
  failure, and HTTP 200 success completion.
- Added `ZSXQFileDownloader._handle_download_response` and reused it from `download_file`.

Behavior impact:

- Intended behavior change: none.
- Response filename override is still evaluated before status-code dispatch, including non-200
  responses.
- HTTP 200 responses still flow through the existing successful-response helper, preserving body
  writing, stop handling, size mismatch retry, finalization, counters, and interval behavior.
- Non-200 responses still record the same HTTP failure detail and retry through the existing outer
  retry loop.
- Updated file-name/path values still persist into later retry attempts after a response-header
  filename override.
- Signed URL lookup, request options, exception cleanup, final failure handling, schema/config/API
  behavior, and public API behavior are unchanged.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_applies_response_filename_override_before_http_failure -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_handle_download_response_preserves_override_http_failure_and_success_paths tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_applies_response_filename_override_before_http_failure tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_finalizes_success_with_status_counters_logs_and_interval tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_marks_final_failure_after_http_retries -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-refactor response-dispatch characterization test passed against the original inline branch.
- `py_compile` passed.
- Focused response-dispatch/download tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 77 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 719 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader overridden partial cleanup repair

Changed:

- Added regression coverage for body-write exceptions after a `Content-Disposition` filename
  override.
- Updated `FakeFailingBodyDownloadResponse` to accept response headers for exception-path tests.
- Updated `ZSXQFileDownloader._handle_download_response` so response-handling exceptions record
  cleanup using the current response-overridden `file_path`.

Behavior impact:

- Intended behavior change: restores pre-refactor behavior for an exception path affected by the
  previous response-dispatch extraction.
- Body-write exceptions after response filename override now remove the overridden `.part` file,
  preserving the earlier inline-order cleanup semantics.
- The existing `download_exception` error code/message, retry count, final failure status update,
  response filename override log, HTTP failure path, success path, size mismatch path, signed URL
  lookup, request options, schema/config/API behavior, and public API behavior are unchanged.
- This does not introduce a new fallback or compatibility path.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_cleans_overridden_partial_file_after_body_exception -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_cleans_overridden_partial_file_after_body_exception tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_cleans_partial_file_after_body_exception_retries tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_handle_download_response_preserves_override_http_failure_and_success_paths tests.test_zsxq_file_downloader_helpers.FileDownloaderDownloadTests.test_download_file_applies_response_filename_override_before_http_failure -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new regression test failed against the previous response-dispatch extraction because
  `real.pdf.part` was left behind, then passed after the cleanup-path repair.
- `py_compile` passed.
- Focused response-dispatch/exception-cleanup tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 78 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 720 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader database download query helper

Changed:

- Added characterization coverage for `download_files_from_database` query construction with date
  filters, status filters, limit parameters, and legacy `order_by` sorting.
- Added characterization coverage for an unfiltered heat-sort query preserving non-numeric group ID
  parameters, no `download_status` predicate, and no `LIMIT` clause.
- Extracted `database_download_query_plan` into `backend/crawlers/zsxq_file_downloader_helpers.py`
  and reused it from `ZSXQFileDownloader.download_files_from_database`.

Behavior impact:

- Intended behavior change: none.
- SQL predicate order, parameter order, group ID conversion call site, default heat sorting,
  create-time sorting, legacy `order_by` mapping, `max_files` limit behavior, empty result stats,
  and user-facing logs are preserved.
- Download iteration, skip/download/failure counters, retry behavior, long sleep, per-file delay,
  status updates, schema/config/API behavior, and public API behavior are unchanged.
- This does not remove or alter the legacy `recent_days` or `order_by` compatibility inputs.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDatabaseDownloadTests -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new database-download query characterization tests passed against the pre-refactor inline
  query construction and after helper extraction.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 80 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 722 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader database row download helper

Changed:

- Added characterization coverage for `download_files_from_database` result handling across
  skipped, successful, and failed per-file download results.
- Locked the database-row-to-download-payload shape and successful-download interval side effects.
- Extracted `ZSXQFileDownloader._download_database_file_row` and reused it from the database
  download loop.

Behavior impact:

- Intended behavior change: none.
- Per-row log messages, file payload shape, skip/download/failure counters, successful-download
  long-delay check, inter-file download delay, final summary logs, empty-result behavior, query
  semantics, schema/config/API behavior, and public API behavior are unchanged.
- The outer `download_files_from_database` loop still owns stop checks plus `KeyboardInterrupt` and
  generic exception handling, preserving the existing stop and continue-after-row-error behavior.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderDatabaseDownloadTests -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new database-download result-handling characterization test passed before and after helper
  extraction.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 81 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 723 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader batch item helper

Changed:

- Added characterization coverage for `download_files_batch` result handling across skipped,
  successful, and failed per-file download results.
- Locked the current batch-download payload pass-through, fetched page arguments, skip/download/fail
  counters, successful-download interval side effects, and repeated display index after a skipped
  file.
- Extracted `ZSXQFileDownloader._download_batch_file_item` and reused it from the batch download
  loop.

Behavior impact:

- Intended behavior change: none.
- Batch start logs, per-file display labels, skip/download/failure counters, total processed count,
  successful-download long-delay check, inter-file download delay, page fetch arguments, final
  summary logs, schema/config/API behavior, and public API behavior are unchanged.
- The outer `download_files_batch` loop still owns stop checks, max-success limit checks, next-page
  sleep, and page traversal, preserving existing pagination and stop semantics.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderBatchDownloadTests -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new batch-download result-handling characterization test passed before and after helper
  extraction.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 82 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 724 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader time dedupe page helper

Changed:

- Added characterization coverage for `collect_files_by_time` when the first page contains both
  files newer than the database latest timestamp and older/equal files.
- Locked the current behavior that old files are filtered before import, only newer files are
  imported, and collection stops after the mixed page without traversing the next page.
- Extracted `time_dedupe_page_plan` into `backend/crawlers/zsxq_file_downloader_helpers.py` and
  reused it from `collect_files_by_time`.

Behavior impact:

- Intended behavior change: none.
- String-based create-time comparison, time analysis logs, old-file filtering, in-place API
  response mutation before import, stop-after-insert behavior, force-refresh hint logs, page count,
  final stats, schema/config/API behavior, and public API behavior are unchanged.
- The outer `collect_files_by_time` loop still owns stop checks, fetch failures, import exception
  handling, stop-before-date checks, next-page sleep, and final stats logging.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_stops_when_page_import_fails -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new mixed-page time-dedupe characterization test passed before and after helper extraction.
- `py_compile` passed.
- Focused mixed-page and import-failure pagination tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 84 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 726 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader time collection final summary helper

Changed:

- Added direct helper coverage for `collect_files_by_time` final summary calculation.
- Locked the final total/new file counts, page count, imported-stat return shape, and positive-only
  log item filtering used by the final collection summary.
- Extracted `time_collection_final_summary` into
  `backend/crawlers/zsxq_file_downloader_helpers.py` and reused it from `collect_files_by_time`.

Behavior impact:

- Intended behavior change: none.
- Final database stat lookup, new-file delta calculation, returned keys, imported-stat expansion,
  positive-only imported-stat logs, positive-only database-state logs, page count, schema/config/API
  behavior, and public API behavior are unchanged.
- The outer `collect_files_by_time` loop still owns stop checks, fetch failures, time dedupe,
  import exception handling, stop-before-date checks, next-page sleep, and final log messages.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderTimeHelperTests.test_time_collection_final_summary_preserves_result_and_positive_log_items tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused final-summary helper and mixed-page collection tests passed.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 85 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 727 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader latest file time query helper

Changed:

- Added characterization assertions for the `collect_files_by_time` database-latest-time lookup
  SQL and numeric group ID parameter.
- Added direct helper coverage for the latest file create-time query shape.
- Extracted `latest_file_create_time_query` into
  `backend/crawlers/zsxq_file_downloader_helpers.py` and reused it from `collect_files_by_time`.

Behavior impact:

- Intended behavior change: none.
- The `SELECT MAX(create_time) FROM files` lookup, `group_id = ?` predicate, non-empty
  `create_time` filter, parameter order, `_query_group_id` conversion call site, latest-time log,
  and time-dedupe trigger conditions are unchanged.
- The outer `collect_files_by_time` loop still owns database cursor execution, result fetch,
  stop checks, page fetch/import behavior, fallback/legacy behavior, schema/config/API behavior,
  and public API behavior.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderTimeHelperTests.test_latest_file_create_time_query_preserves_shape_and_params tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new query-shape characterization assertion passed before helper extraction.
- Focused latest-time helper and mixed-page collection tests passed after extraction.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 86 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 728 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader time collection mode helper

Changed:

- Added direct helper coverage for `collect_files_by_time` mode selection across default time
  dedupe, force refresh, stop-before date, and non-create-time sort modes.
- Extracted `time_collection_mode` into `backend/crawlers/zsxq_file_downloader_helpers.py` and
  reused it from `collect_files_by_time`.

Behavior impact:

- Intended behavior change: none.
- `force_refresh` precedence, `sort == "by_create_time"` dedupe gating, stop-before-date dedupe
  suppression, mode log text, mode log ordering, schema/config/API behavior, and public API
  behavior are unchanged.
- The outer `collect_files_by_time` method still owns initial start/boundary logs, stop checks,
  database stats, latest-time lookup, page fetch/import, fallback/legacy behavior, and final
  summary.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderTimeHelperTests.test_time_collection_mode_preserves_dedupe_and_force_refresh_rules tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused mode helper and mixed-page collection tests passed.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 87 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 729 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P9 file downloader next-page plan helper

Changed:

- Added a characterization test for `collect_files_by_time` next-page behavior before changing
  production code.
- Locked the first-page `next_index` handoff to the second page request, one page-between sleep,
  next-page log message, terminal last-page log message, and two-page result count.
- Extracted `time_collection_next_page_plan` into
  `backend/crawlers/zsxq_file_downloader_helpers.py` and reused it from `collect_files_by_time`.

Behavior impact:

- Intended behavior change: none.
- Truthy `next_index` handling, falsy terminal-page handling, log text, sleep timing call site,
  random delay range, page count, fetch argument order, schema/config/API behavior, and public API
  behavior are unchanged.
- The outer `collect_files_by_time` method still owns fetch/import side effects, stop checks,
  time-dedupe filtering, stop-before-date checks, sleep execution, fallback/legacy behavior, and
  final summary.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_preserves_next_index_sleep_and_last_page_log tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers.FileDownloaderTimeHelperTests.test_time_collection_next_page_plan_preserves_messages_and_next_index tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_preserves_next_index_sleep_and_last_page_log tests.test_zsxq_file_downloader_helpers.FileDownloaderPaginationTests.test_collect_files_by_time_filters_old_files_and_stops_after_mixed_page -v
uv run python -m py_compile backend\crawlers\zsxq_file_downloader.py backend\crawlers\zsxq_file_downloader_helpers.py tests\test_zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- The new next-page characterization test passed before helper extraction.
- Focused next-page helper, next-page collection, and mixed-page collection tests passed after
  extraction.
- `py_compile` passed.
- `tests.test_zsxq_file_downloader_helpers`: 89 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 731 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl stats helper

Changed:

- Added direct helper coverage for the official crawl cumulative stats payload.
- Extracted `_empty_official_crawl_stats` in `backend/services/crawl_service.py` and reused it
  from both official time-range and official pages crawl paths.

Behavior impact:

- Intended behavior change: none.
- Official crawl result keys, default numeric values, `source: official`, duplicate counting,
  update-task payload shape, official request/import loops, cursor handling, task stop checks,
  schema/config/API behavior, and public API behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior; the cookie-based legacy
  crawler branch is untouched.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_empty_official_crawl_stats_preserves_shape_and_independent_instances -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official stats helper test passed.
- `tests.test_crawl_routes_helpers`: 17 tests passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 733 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl page stats helper

Changed:

- Added direct helper coverage for official crawl per-page stats accumulation.
- Extracted `_add_official_page_stats` in `backend/services/crawl_service.py` and reused it
  from both official time-range and official pages crawl paths.

Behavior impact:

- Intended behavior change: none.
- `new_topics`, `updated_topics`, `errors`, and `pages` accumulation semantics are unchanged;
  duplicate counting, `source: official`, update-task payload shape, official request/import
  loops, cursor handling, task stop checks, schema/config/API behavior, and public API behavior
  are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior; the cookie-based legacy
  crawler branch is untouched.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_add_official_page_stats_preserves_accumulation_semantics -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official page stats helper test passed.
- `tests.test_crawl_routes_helpers`: 18 tests passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 734 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl page dedupe helper

Changed:

- Added direct helper coverage for official crawl page-level topic de-duplication.
- Extracted `_dedupe_official_page_topics` in `backend/services/crawl_service.py` and reused it
  from both official time-range and official pages crawl paths.

Behavior impact:

- Intended behavior change: none.
- Topic order, first-seen topic retention, duplicate counting, and the existing missing/zero
  `topic_id` behavior are unchanged.
- Time-range filtering still happens after de-duplication, and latest-mode existing-topic checks
  still happen after de-duplication.
- Official request/import loops, cursor handling, task stop checks, schema/config/API behavior,
  public API behavior, and legacy cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_dedupe_official_page_topics_preserves_seen_and_missing_id_semantics -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official page de-duplication helper test passed.
- `tests.test_crawl_routes_helpers`: 19 tests passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 735 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl next-page cursor helper

Changed:

- Added direct helper coverage for official crawl next-page continuation semantics.
- Extracted `_official_next_page_cursor` in `backend/services/crawl_service.py` and reused it
  from both official time-range and official pages crawl paths.

Behavior impact:

- Intended behavior change: none.
- Pagination still stops when `has_more` is false, `next_end_time` is missing, or the cursor does
  not advance.
- The existing `_official_page_cursor` behavior remains covered separately; request/import loops,
  duplicate handling, stats accumulation, stop checks, log text, update-task payloads,
  schema/config/API behavior, public API behavior, and legacy cookie-based crawler behavior are
  unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_next_page_cursor_requires_has_more_and_moving_cursor -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers.OfficialTopicClientHelperTests.test_official_page_cursor_stops_when_cursor_does_not_move -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official next-page cursor helper test passed.
- `tests.test_crawl_routes_helpers`: 20 tests passed.
- Existing `_official_page_cursor` focused test passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 736 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl per-page limit helper

Changed:

- Added direct helper coverage for the official crawl per-page default and API cap.
- Extracted `_official_per_page_limit` in `backend/services/crawl_service.py` and reused it
  from both official time-range and official pages crawl paths.

Behavior impact:

- Intended behavior change: none.
- Official requests still default missing or zero `per_page` values to `20` and cap values above
  `30` at `30`.
- The time-range path still logs the existing "official API page cap is treated as 30" message only
  when the request explicitly provides a value above `30`.
- Request/import loops, pagination cursor handling, duplicate handling, stats accumulation,
  stop checks, update-task payloads, schema/config/API behavior, public API behavior, and legacy
  cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_per_page_limit_preserves_default_and_cap -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official per-page limit helper test passed.
- `tests.test_crawl_routes_helpers`: 21 tests passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 737 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl time-range filter helper

Changed:

- Added direct helper coverage for official crawl time-range topic filtering.
- Extracted `_filter_official_topics_by_time_range` in `backend/services/crawl_service.py` and
  reused it from the official time-range crawl path after page-level de-duplication.

Behavior impact:

- Intended behavior change: none.
- Time range bounds remain inclusive, invalid or missing `create_time` values are still ignored,
  and the returned `oldest_dt` remains the last valid topic time observed on the page.
- De-duplication still happens before time filtering, and the "reached before start time" stop
  condition still uses the same `oldest_dt` value as before.
- Request/import loops, pagination cursor handling, duplicate handling, stats accumulation,
  stop checks, update-task payloads, schema/config/API behavior, public API behavior, and legacy
  cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_filter_official_topics_by_time_range_preserves_bounds_and_oldest_time -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official time-range filter helper test passed.
- `tests.test_crawl_routes_helpers`: 22 tests passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 738 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official latest new-topic helper

Changed:

- Added direct helper coverage for official latest-mode new-topic filtering.
- Extracted `_new_official_topics` in `backend/services/crawl_service.py` and reused it
  from the official pages crawl path when `mode == "latest"`.

Behavior impact:

- Intended behavior change: none.
- The existing `_official_topic_exists` query remains the source of truth for whether a topic is
  already stored.
- Topic order, `topic_id` integer coercion, missing/zero `topic_id` behavior, latest-mode page
  analysis log counts, "all topics already exist" stop condition, import selection, update-task
  payloads, schema/config/API behavior, public API behavior, and legacy cookie-based crawler
  behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_new_official_topics_preserves_existing_check_order_and_missing_id_semantics -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official latest new-topic helper test passed.
- `tests.test_crawl_routes_helpers`: 23 tests passed.
- `py_compile` passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 739 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl completion message helper

Changed:

- Added direct helper coverage for official crawl completion message mapping.
- Added `OFFICIAL_CRAWL_COMPLETION_MESSAGES` and `_official_crawl_completion_message` in
  `backend/services/crawl_service.py`.
- Replaced the inline completion-message dictionary in `_run_official_crawl_pages_task` with the
  helper call.

Behavior impact:

- Intended behavior change: none.
- The `latest`, `incremental`, `all`, and unknown-mode completion messages remain unchanged.
- `update_task()` still receives status `completed`, the same message string for each mode, and the
  same `total_stats` payload.
- Request/import loops, pagination cursor handling, duplicate handling, latest-mode existing-topic
  stop behavior, schema/config/API behavior, public API behavior, and legacy cookie-based crawler
  behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_crawl_completion_message_preserves_mode_mapping -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official crawl completion message helper test passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 24 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 740 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official start cursor timestamp helper

Changed:

- Added direct helper coverage for official oldest-timestamp cursor conversion.
- Extracted `_official_cursor_before_timestamp` in `backend/services/crawl_service.py`.
- Reused the helper from `_official_start_cursor_from_oldest` after the existing database timestamp
  lookup and log.

Behavior impact:

- Intended behavior change: none.
- Valid `+0800` and `+08:00` timestamps still convert to the previous millisecond and format as
  Beijing-time `YYYY-MM-DDTHH:MM:SS.mmm+0800`.
- Invalid oldest timestamps still fall back to the original timestamp string.
- Empty-database handling, the `allow_empty` sentinel behavior, task log messages, official
  historical/all route behavior, update-task failure semantics, schema/config/API behavior, public
  API behavior, and legacy cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_cursor_before_timestamp_preserves_offset_and_fallback -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official cursor-before-timestamp helper test passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 25 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 741 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official crawl stop condition helpers

Changed:

- Added direct helper coverage for official pages remaining and time-range before-start stop
  conditions.
- Extracted `_official_pages_remaining` and `_official_reached_before_start` in
  `backend/services/crawl_service.py`.
- Reused the helpers from the official pages crawl loop and official time-range crawl loop.

Behavior impact:

- Intended behavior change: none.
- `pages is None` still means unbounded official pages crawling and does not require a `pages` key
  in the stats payload.
- Bounded official pages crawling still stops when `total_stats["pages"] >= pages`.
- Official time-range crawling still stops only when the oldest valid topic timestamp is strictly
  before `start_dt`; `None`, equal, and later timestamps keep the existing behavior.
- Request/import loops, pagination cursor handling, duplicate handling, latest-mode existing-topic
  stop behavior, log messages, update-task payloads, schema/config/API behavior, public API
  behavior, and legacy cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_pages_remaining_preserves_unbounded_and_limit_semantics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_reached_before_start_preserves_none_equal_and_older_semantics -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official stop condition helper tests passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 27 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 743 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official topic ID helper

Changed:

- Added direct helper coverage for official topic ID integer coercion.
- Extracted `_official_topic_id` in `backend/services/crawl_service.py`.
- Reused the helper from official latest new-topic filtering, official import, and official page
  de-duplication.

Behavior impact:

- Intended behavior change: none.
- Missing and falsey `topic_id` values still coerce to `0`.
- Numeric string and integer `topic_id` values still coerce through `int(...)`.
- Invalid non-numeric topic IDs still raise the same conversion error instead of being swallowed.
- Existing missing/zero ID duplicate semantics, latest-mode existence checks, official import
  comment fetch topic IDs, request/import loops, pagination cursor handling, log messages,
  update-task payloads, schema/config/API behavior, public API behavior, and legacy cookie-based
  crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topic_id_preserves_integer_coercion_and_invalid_error -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official topic ID helper test passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 28 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 744 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official comment count helper

Changed:

- Added characterization coverage for official import comment-count handling, comment fetch calls,
  normalization comment payloads, import-result stats, and final commit behavior.
- Added direct helper coverage for official topic comment-count integer coercion.
- Extracted `_official_topic_comments_count` in `backend/services/crawl_service.py`.
- Reused the helper from `_official_import_topics`.

Behavior impact:

- Intended behavior change: none.
- Missing `counts`, falsey `counts`, and falsey `counts.comments` still coerce to `0`.
- Numeric string and integer comment counts still coerce through `int(...)`.
- Invalid non-numeric comment counts still raise the same conversion error instead of being
  swallowed.
- Topics with positive comment counts still fetch official comments, log the same success message,
  and pass the fetched comments to `normalize_official_topic`.
- Topics with zero or missing comment counts still skip comment fetch and pass `comments=None` to
  `normalize_official_topic`.
- `_official_import_topics` still returns the same `new_topics`/`updated_topics`/`errors` stats and
  commits once after processing the batch.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topic_comments_count_preserves_integer_coercion_and_invalid_error tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_import_topics_preserves_comment_count_stats_and_commit -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official comment-count helper and import characterization tests passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 30 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 746 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official import result helper

Changed:

- Added direct helper coverage for official import result-to-stats mapping.
- Extracted `_add_official_import_result` in `backend/services/crawl_service.py`.
- Reused the helper from `_official_import_topics`.

Behavior impact:

- Intended behavior change: none.
- `new` import results still increment `new_topics`.
- `updated` import results still increment `updated_topics`.
- `error` and any other import result value still increment `errors`.
- Existing comment-count parsing, comment fetch behavior, normalization comment payloads,
  import-topic call order, batch commit behavior, official request/import loops, update-task
  payloads, schema/config/API behavior, public API behavior, and legacy cookie-based crawler
  behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_add_official_import_result_preserves_status_mapping tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_import_topics_preserves_comment_count_stats_and_commit -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official import result helper test passed.
- Existing official import characterization test passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 31 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 747 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official import existence helper reuse

Changed:

- Added characterization coverage for `_official_import_topic` existence-query parameters, numeric
  group ID conversion, missing-topic-ID behavior, import call order, and import result mapping.
- Reused `_official_topic_exists` inside `_official_import_topic`.
- Broadened `_official_topic_exists` topic-ID parameter typing to reflect current callers that pass
  integer IDs, string IDs, and missing IDs.

Behavior impact:

- Intended behavior change: none.
- `_official_import_topic` still checks existence before calling `import_topic_data`.
- Existing topics still return `updated` after a successful import.
- Missing existing rows still return `new` after a successful import.
- Failed imports still return `error`, regardless of the existence check result.
- The existence query SQL, group ID normalization, query parameter order, missing `topic_id`
  behavior, official request/import loops, update-task payloads, schema/config/API behavior, public
  API behavior, and legacy cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_import_topic_preserves_existence_query_group_id_and_result_mapping tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_import_topics_preserves_comment_count_stats_and_commit -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official import-topic characterization test passed before and after helper reuse.
- Existing official import batch characterization test passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 32 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 748 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official incremental cursor helper

Changed:

- Added characterization coverage for the official historical and official incremental entrypoint
  branches that start from the oldest stored topic cursor.
- Extracted `_run_official_incremental_pages_from_oldest` in
  `backend/services/crawl_service.py`.
- Reused the helper from `run_crawl_historical_task` and `run_crawl_incremental_task`.

Behavior impact:

- Intended behavior change: none.
- Historical and incremental official branches still emit their existing entry logs.
- Both branches still create `ZSXQDatabase(group_id)`, call `_official_start_cursor_from_oldest`
  with `allow_empty=False`, and skip the legacy cookie crawler path.
- Empty-database failures still update the same failed status and user-facing message for each
  entrypoint.
- Successful official historical/incremental branches still call `_run_official_crawl_pages_task`
  with mode `incremental`, the same `pages`/`per_page`, and the same `start_cursor` keyword.
- Public API behavior, task status semantics, update-task payloads, schema/config behavior, and
  legacy cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_historical_branch_uses_oldest_cursor_and_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_incremental_branch_uses_oldest_cursor_and_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_incremental_empty_database_fails_without_legacy_crawler -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official historical and incremental entrypoint characterization tests passed before and after
  helper extraction.
- Existing official incremental empty-database test passed.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 34 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 750 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official all cursor helper

Changed:

- Added characterization coverage for the official all-crawl entrypoint branch that starts from
  the oldest stored topic cursor when data exists.
- Extracted `_run_official_all_pages_from_oldest` in `backend/services/crawl_service.py`.
- Reused the helper from `run_crawl_all_task`.

Behavior impact:

- Intended behavior change: none.
- The official all-crawl branch still emits its existing running status, warning logs, and official
  branch log before dispatch.
- The branch still creates `ZSXQDatabase(group_id)`, calls `_official_start_cursor_from_oldest`
  with `allow_empty=True`, and skips the legacy cookie crawler path.
- Empty-database behavior remains unchanged because `allow_empty=True` still allows a `None`
  cursor to flow into the official pages runner instead of failing the task.
- Successful official all-crawl dispatch still calls `_run_official_crawl_pages_task` with
  `pages=None`, `per_page=20`, mode `all`, and the same `start_cursor` keyword.
- Public API behavior, task status semantics, update-task payloads, schema/config behavior, and
  legacy cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_all_branch_uses_oldest_cursor_and_skips_legacy_crawler -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_all_branch_uses_oldest_cursor_and_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_historical_branch_uses_oldest_cursor_and_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_incremental_branch_uses_oldest_cursor_and_skips_legacy_crawler -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New official all-crawl entrypoint characterization test passed before and after helper extraction.
- Existing official historical and incremental cursor branch tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 35 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 751 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy crawler preparation helper

Changed:

- Added characterization coverage for the legacy latest-crawl entrypoint branch.
- Extracted `_prepare_legacy_crawler` in `backend/services/crawl_service.py`.
- Reused the helper from the historical, all, incremental, latest, and time-range legacy branches.

Behavior impact:

- Intended behavior change: none.
- Legacy branches still build task callbacks, create the cookie-based `ZSXQTopicCrawler`, set its
  stop-check callback, register it with task runtime, and apply crawl settings before startup logs.
- Time-range legacy crawling still passes `require_overrides=True` when applying interval settings.
- Existing stop checks, initialization-stopped logging, startup logs, crawl method calls, expired
  handling, completion logs, failure messages, and `finally` unregistration remain in their original
  entrypoint-specific locations.
- Public API behavior, task status semantics, update-task payloads, schema/config behavior, and
  official MCP HTTP crawler behavior are unchanged.
- This does not remove legacy behavior; it isolates the retained cookie-based crawler setup.
- This does not introduce, remove, or alter fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_latest_branch_creates_registered_crawler_and_applies_settings -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_latest_branch_creates_registered_crawler_and_applies_settings tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_latest_branch_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_all_branch_uses_oldest_cursor_and_skips_legacy_crawler -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New legacy latest entrypoint characterization test passed before and after helper extraction.
- Existing time-range legacy empty-page test and official branch tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 36 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 752 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range filter helper

Changed:

- Added characterization coverage for the legacy time-range entrypoint filtering mixed valid and
  invalid topic timestamps.
- Extracted `_filter_legacy_topics_by_time_range` in `backend/services/crawl_service.py`.
- Reused the helper from the legacy `run_crawl_time_range_task` page loop.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range crawling still parses topic `create_time` values with the existing `+0800`
  normalization and invalid timestamp fallback.
- Invalid timestamps are still ignored for filtering and for the last-topic-time stop check.
- The filtered payload sent to `store_batch_data`, page stats accumulation, page count increment,
  next-page `end_time` adjustment, long-delay call, and empty-page completion behavior are unchanged.
- Public API behavior, task status semantics, update-task payloads, schema/config behavior, official
  MCP HTTP crawler behavior, and cookie-based crawler behavior are unchanged.
- This does not introduce, remove, or alter legacy/fallback behavior.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New legacy time-range characterization test passed before and after helper extraction.
- Existing legacy empty-page time-range test passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 37 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 753 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy next-end-time helper

Changed:

- Added characterization coverage for the legacy time-range next-page cursor fallback when the
  oldest topic timestamp is invalid.
- Extracted `_legacy_next_end_time` in `backend/services/crawl_service.py`.
- Reused the helper from the legacy `run_crawl_time_range_task` page loop.

Behavior impact:

- Intended behavior change: none.
- Valid oldest topic timestamps still normalize `+0800` to `+08:00`, subtract
  `crawler.timestamp_offset_ms`, and format back to `YYYY-MM-DDTHH:MM:SS.mmm+0800`.
- Invalid or missing oldest topic timestamps still fall back to the original `oldest_in_page`
  value for the next request `end_time`.
- Filtering, page stats, stop checks, long-delay calls, empty-page completion, public API behavior,
  task status semantics, schema/config behavior, official MCP HTTP behavior, and cookie-based
  crawler behavior are unchanged.
- No legacy/fallback behavior was removed; the fallback is now covered by a focused test.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New fallback test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 38 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 754 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range page store helper

Changed:

- Added characterization coverage for a legacy time-range page whose topics are all outside the
  requested time range.
- Extracted `_store_legacy_time_range_page` in `backend/services/crawl_service.py`.
- Reused the helper from the legacy `run_crawl_time_range_task` page loop.

Behavior impact:

- Intended behavior change: none.
- Filtered topics are still wrapped in the same `{"succeeded": True, "resp_data": {"topics": ...}}`
  payload before calling `crawler.store_batch_data`.
- `new_topics`, `updated_topics`, and `errors` still use the same `.get(..., 0)` accumulation
  semantics from the crawler's store result.
- Pages that contain topics but no in-range topics still skip storage, still count as one processed
  page, and still continue through the existing next-cursor and long-delay path.
- Empty API pages still complete without incrementing `pages`.
- Retry handling, expired handling, stop checks, next-page cursor computation, start-time stop
  behavior, public API behavior, task status semantics, schema/config behavior, official MCP HTTP
  behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New out-of-range page characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 39 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 755 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range fetch failure helper

Changed:

- Added characterization coverage for a legacy time-range page fetch that fails once and then
  succeeds with an empty page.
- Extracted `_record_legacy_time_range_fetch_failure` in `backend/services/crawl_service.py`.
- Reused the helper from the legacy `run_crawl_time_range_task` retry branch.

Behavior impact:

- Intended behavior change: none.
- Failed page fetches still increment retry before logging, increment `total_stats["errors"]`, and
  log `❌ 页面获取失败 (重试{retry}/{max_retries_per_page})`.
- The retry loop still continues immediately after recording the failure.
- A later empty page still completes with `pages` unchanged.
- Max-retry termination, expired handling, stop checks, filtered topic storage, next-page cursor
  computation, long-delay behavior, public API behavior, task status semantics, schema/config
  behavior, official MCP HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New retry characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 40 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 756 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range expired helper

Changed:

- Added characterization coverage for a legacy time-range expired response returned from
  `fetch_topics_safe`.
- Extracted `_mark_legacy_time_range_expired` in `backend/services/crawl_service.py`.
- Reused the helper from the legacy `run_crawl_time_range_task` expired branch.

Behavior impact:

- Intended behavior change: none.
- The expired branch still logs `❌ 会员已过期: {message}` using `data.get("message")`.
- The expired branch still calls `update_task(task_id, "failed", "会员已过期", data)` with the
  original response payload unchanged.
- The task still returns immediately after marking failed, skips completion status, and still
  unregisters the task crawler in `finally`.
- This helper intentionally does not reuse `_mark_expired_task`, because that helper reshapes the
  failure payload for other crawl modes.
- Retry handling, filtered topic storage, next-page cursor computation, stop checks, public API
  behavior, task status semantics, schema/config behavior, official MCP HTTP behavior, and
  cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New expired-response characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 41 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 757 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range page failure helper

Changed:

- Added characterization coverage for a legacy time-range page that fails all 10 fetch retries.
- Extracted `_legacy_time_range_page_failed` in `backend/services/crawl_service.py`.
- Reused the helper from the legacy `run_crawl_time_range_task` outer page loop.

Behavior impact:

- Intended behavior change: none.
- The retry loop still attempts exactly 10 failed fetches for the current page.
- Each failed fetch still increments `total_stats["errors"]`; after 10 failures the final
  completed payload still reports `errors: 10` and `pages: 0`.
- The terminal log remains `🚫 当前页面达到最大重试次数，终止任务`.
- The task still exits the page loop and then calls `update_task(task_id, "completed",
  "时间区间爬取完成", total_stats)`.
- Expired handling, retry logging, filtered topic storage, next-page cursor computation, stop
  checks, public API behavior, task status semantics, schema/config behavior, official MCP HTTP
  behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New max-retry characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 42 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 758 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range before-start helper

Changed:

- Added characterization coverage for a legacy time-range page whose oldest valid topic is before
  the requested start time.
- Extracted `_legacy_time_range_reached_before_start` in `backend/services/crawl_service.py`.
- Reused the helper for both the inner page-loop log branch and the outer loop exit branch.

Behavior impact:

- Intended behavior change: none.
- The branch still logs `✅ 已到达起始时间之前，任务结束` only after a page with topics is
  processed and the last valid topic timestamp is strictly before `start_dt`.
- Such a page still counts as one processed page, skips storage when no topics are in range, does
  not call `check_page_long_delay`, exits the outer loop, and completes with the same stats payload.
- Empty-page completion, max-retry handling, expired handling, retry logging, filtered topic
  storage, next-page cursor computation, stop checks, public API behavior, task status semantics,
  schema/config behavior, official MCP HTTP behavior, and cookie-based crawler behavior are
  unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New before-start characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- `tests.test_crawl_routes_helpers`: 43 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 759 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range empty-page helper

Changed:

- Reused the existing empty-page characterization coverage in `tests.test_crawl_routes_helpers`.
- Extracted `_legacy_time_range_page_empty` in `backend/services/crawl_service.py`.
- Kept `page_processed`, `reached_end`, and loop `break` assignments at the original call site so
  the legacy control flow remains visible and unchanged.

Behavior impact:

- Intended behavior change: none.
- Empty legacy time-range pages still log `📭 无更多数据，任务结束`, do not increment page stats,
  exit the outer crawl loop, and complete with the same stats payload.
- Fetch retry, expired handling, filtered topic storage, before-start stopping, next-page cursor
  computation, stop checks, public API behavior, task status semantics, schema/config behavior,
  official MCP HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Existing empty-page characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 43 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 759 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range outer stop helper

Changed:

- Added characterization coverage for the legacy time-range outer stop branch.
- Extracted `_legacy_time_range_task_stopped` in `backend/services/crawl_service.py`.
- Kept the inner retry-loop `is_task_stopped` check unchanged because it previously exited without
  logging the outer stop message.

Behavior impact:

- Intended behavior change: none.
- A legacy time-range task that is stopped before fetching a page still logs `🛑 任务已停止`, performs
  no fetch, and then completes with the existing zeroed stats payload.
- This intentionally preserves the current compatibility behavior where this stop path reaches the
  normal `"completed"` task update instead of changing public task status semantics.
- Empty-page completion, fetch retry, expired handling, filtered topic storage, before-start
  stopping, next-page cursor computation, public API behavior, schema/config behavior, official MCP
  HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New outer-stop characterization test passed before and after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range fetch helper

Changed:

- Reused existing characterization coverage that checks the legacy time-range
  `fetch_topics_safe` call parameters.
- Extracted `_fetch_legacy_time_range_page` in `backend/services/crawl_service.py`.
- Kept retry, stop, expired, empty-page, and response handling at the original call site.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range page fetches still pass `scope="all"`, the requested/default page count,
  the formatted begin/end timestamps, and `is_historical=True`.
- `end_time_param` still accepts the original formatted end time or later cursor values produced by
  `_legacy_next_end_time`, including fallback strings for invalid timestamps.
- Fetch retry, expired handling, empty-page completion, filtered topic storage, before-start
  stopping, next-page cursor computation, stop checks, public API behavior, task status semantics,
  schema/config behavior, official MCP HTTP behavior, and cookie-based crawler behavior are
  unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Existing fetch-parameter characterization coverage passed after helper extraction.
- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range topics helper

Changed:

- Reused existing legacy time-range coverage for empty pages, filtered pages, retry paths, and
  expired responses.
- Extracted `_legacy_time_range_topics` in `backend/services/crawl_service.py`.
- Kept the empty-page, filtering, storage, cursor, and stop decisions at the original call site.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range responses still read topics from `data["resp_data"]["topics"]` when present.
- Missing or null `resp_data`, missing `topics`, or null `topics` still fall back to an empty list
  and therefore use the existing empty-page completion path.
- The helper does not add new defensive handling for impossible internal response shapes, so legacy
  truthy non-dict failures remain governed by the surrounding exception path.
- Fetch retry, expired handling, empty-page completion, filtered topic storage, before-start
  stopping, next-page cursor computation, stop checks, public API behavior, task status semantics,
  schema/config behavior, official MCP HTTP behavior, and cookie-based crawler behavior are
  unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused legacy time-range tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range page summary log helper

Changed:

- Reused existing legacy time-range tests that assert the page summary log messages.
- Extracted `_log_legacy_time_range_page_summary` in `backend/services/crawl_service.py`.
- Kept filtering, storage, cursor, delay, and stop decisions at the original call site.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range pages still log `📄 本页获取 {len(topics)} 个话题，区间内 {len(filtered)} 个`
  after filtering and before storage.
- Empty pages, out-of-range pages, filtered page storage, before-start stopping, retry handling,
  expired handling, public API behavior, task status semantics, schema/config behavior, official MCP
  HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused log-message tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range stats helper

Changed:

- Reused existing legacy time-range tests that assert completed stats payloads across empty,
  filtered, retry, max-retry, and outer-stop paths.
- Extracted `_empty_legacy_time_range_stats` in `backend/services/crawl_service.py`.
- Kept all stats mutation, page counting, retry error counting, and task completion decisions at
  the original call sites.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range tasks still start with
  `{"new_topics": 0, "updated_topics": 0, "errors": 0, "pages": 0}`.
- Empty pages, filtered page storage, retry failures, max-retry failures, outer-stop completion,
  before-start stopping, expired handling, public API behavior, task status semantics,
  schema/config behavior, official MCP HTTP behavior, and cookie-based crawler behavior are
  unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused stats-payload tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range initial cursor helper

Changed:

- Reused existing legacy time-range tests that assert the first fetch `begin_time`/`end_time`
  parameters and the second-page `end_time` cursor update.
- Extracted `_legacy_time_range_initial_cursors` in `backend/services/crawl_service.py`.
- Kept `_format_zsxq_time` formatting, next-page cursor mutation, retry handling, and fetch call
  construction at their existing behavior boundaries.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range tasks still initialize `begin_time` from `start_dt` and `end_time` from
  `end_dt` using the original ZSXQ timestamp format.
- Empty pages, filtered page storage, invalid timestamp fallback, retry failures, max-retry
  failures, outer-stop completion, before-start stopping, expired handling, public API behavior,
  task status semantics, schema/config behavior, official MCP HTTP behavior, and cookie-based
  crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused fetch-cursor tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range max-retry constant

Changed:

- Reused existing legacy time-range retry tests that assert one failed-page retry, ten max-retry
  fetch attempts, retry log text, and final stats.
- Added `LEGACY_TIME_RANGE_MAX_RETRIES_PER_PAGE` in `backend/services/crawl_service.py`.
- Replaced the inline `10` max-retry value in `run_crawl_time_range_task` with the named constant.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range failed-page retries still stop after 10 attempts and keep the same
  `重试{retry}/10` log text.
- Retry error counting, max-retry termination, empty pages, filtered page storage, invalid timestamp
  fallback, outer-stop completion, before-start stopping, expired handling, public API behavior,
  task status semantics, schema/config behavior, official MCP HTTP behavior, and cookie-based
  crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused retry and max-retry tests passed after constant extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 44 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 760 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range per-page helper

Changed:

- Added characterization coverage for legacy time-range requests that omit `perPage`, asserting
  the first fetch still uses `count: 20`.
- Added `LEGACY_TIME_RANGE_DEFAULT_PER_PAGE` and `_legacy_time_range_per_page` in
  `backend/services/crawl_service.py`.
- Replaced the inline `request.perPage or 20` expression in `run_crawl_time_range_task` with the
  helper.

Behavior impact:

- Intended behavior change: none.
- Legacy time-range requests without `perPage` still fetch 20 topics per page.
- Explicit `perPage`, fetch call shape, initial cursor formatting, retry error counting,
  max-retry termination, empty pages, filtered page storage, invalid timestamp fallback,
  outer-stop completion, before-start stopping, expired handling, public API behavior, task status
  semantics, schema/config behavior, official MCP HTTP behavior, and cookie-based crawler behavior
  are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_uses_default_per_page_when_missing -v
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_uses_default_per_page_when_missing tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- New default-per-page characterization test passed before helper extraction.
- Focused default-per-page and explicit-per-page tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range finish condition helper

Changed:

- Reused existing legacy time-range tests that assert empty-page termination, filtered-page
  continuation, and before-start termination.
- Extracted `_legacy_time_range_should_finish` in `backend/services/crawl_service.py`.
- Replaced the outer-loop `reached_end or before-start` expression with the helper.

Behavior impact:

- Intended behavior change: none.
- Empty pages still end the legacy time-range task through the existing completion path.
- Pages older than the start time still log `✅ 已到达起始时间之前，任务结束` inside the page loop
  and then stop the outer loop.
- Filtered pages that remain within range still continue to the next legacy page.
- Fetch call shape, initial cursor formatting, default and explicit `perPage`, retry error counting,
  max-retry termination, filtered page storage, invalid timestamp fallback, outer-stop completion,
  expired handling, public API behavior, task status semantics, schema/config behavior, official MCP
  HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused empty-page, filtered-page continuation, and before-start tests passed after helper
  extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range before-start log helper

Changed:

- Reused existing legacy time-range tests that assert before-start log/termination, filtered-page
  continuation, and empty-page termination.
- Extracted `_legacy_time_range_reached_before_start_with_log` in
  `backend/services/crawl_service.py`.
- Kept the outer finish predicate pure so before-start logging still happens only inside the page
  loop.

Behavior impact:

- Intended behavior change: none.
- Pages older than the start time still log `✅ 已到达起始时间之前，任务结束` exactly through the
  existing page-loop path.
- Empty pages, filtered-page continuation, outer finish checks, fetch call shape, initial cursor
  formatting, default and explicit `perPage`, retry error counting, max-retry termination,
  filtered page storage, invalid timestamp fallback, outer-stop completion, expired handling,
  public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Focused before-start, filtered-page continuation, and empty-page tests passed after helper
  extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range expired response helper

Changed:

- Reused existing legacy time-range characterization coverage for expired responses, retryable
  empty fetch responses, empty pages, and normal filtered pages.
- Extracted `_legacy_time_range_response_expired` in `backend/services/crawl_service.py`.
- Kept the original expired predicate semantics: only truthy dict responses with `expired` set are
  marked failed as membership-expired responses.

Behavior impact:

- Intended behavior change: none.
- Expired responses still log `❌ 会员已过期: <message>` and fail the task with the original
  payload.
- Empty/falsey fetch responses still enter the retry/error-count path.
- Non-expired dict responses still flow into topic extraction, empty-page handling, filtering,
  storage, cursor updates, and before-start termination exactly as before.
- Public API behavior, task status semantics, fetch call shape, retry behavior, max-retry
  termination, empty-page completion, filtered page storage, invalid timestamp fallback,
  before-start stopping, schema/config behavior, official MCP HTTP behavior, and cookie-based
  crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction expired characterization test passed.
- Focused expired, retryable empty fetch, empty-page, and filtered-page tests passed after helper
  extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range non-empty page helper

Changed:

- Reused existing legacy time-range characterization coverage for filtered-page continuation,
  invalid oldest timestamp cursor fallback, out-of-range pages with no stored topics, and
  before-start termination.
- Extracted `_process_legacy_time_range_non_empty_page` in
  `backend/services/crawl_service.py`.
- Kept the original non-empty-page side-effect order: filter topics, log page summary, store
  filtered topics, compute next end-time cursor, evaluate/log before-start termination, then run
  the crawler long-delay check only when before-start was not reached.

Behavior impact:

- Intended behavior change: none.
- Filtered topics, page stats, page summary logs, `end_time` cursor updates, invalid timestamp
  fallback, before-start logging, and `check_page_long_delay` call conditions are unchanged.
- Empty pages, expired responses, retry failures, max-retry termination, outer-stop completion,
  public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction focused filtered-page, invalid-cursor, out-of-range, and before-start tests passed.
- The same focused tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range non-empty page result

Changed:

- Reused existing legacy time-range characterization coverage for filtered-page continuation,
  invalid oldest timestamp cursor fallback, out-of-range pages with no stored topics, and
  before-start termination.
- Added `_LegacyTimeRangeNonEmptyPageResult` in `backend/services/crawl_service.py`.
- Changed `_process_legacy_time_range_non_empty_page` from a positional tuple return to a named
  result with `last_time_dt_in_page`, `end_time_param`, and `reached_before_start`.

Behavior impact:

- Intended behavior change: none.
- The helper still returns the same three control values used by the outer loop; only the internal
  representation changed from positional unpacking to named fields.
- Filtered topics, page stats, page summary logs, `end_time` cursor updates, invalid timestamp
  fallback, before-start logging, `check_page_long_delay` call conditions, empty pages, expired
  responses, retry behavior, public API behavior, task status semantics, schema/config behavior,
  official MCP HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-change focused filtered-page, invalid-cursor, out-of-range, and before-start tests passed.
- The same focused tests passed after replacing the positional tuple with a named result.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range page helper

Changed:

- Reused existing legacy time-range characterization coverage for retryable empty fetches,
  max-retry termination, expired responses, empty pages, normal filtered pages, before-start
  termination, and outer-stop completion.
- Added `_LegacyTimeRangePageResult` and `_process_legacy_time_range_page` in
  `backend/services/crawl_service.py`.
- Moved the inner legacy page fetch/retry/expired/empty/non-empty handling loop out of
  `run_crawl_time_range_task`, leaving the outer loop responsible for task stop checks,
  page-failed handling, finish checks, and final task completion.

Behavior impact:

- Intended behavior change: none.
- Empty/falsey fetch responses still increment retry errors and retry up to
  `LEGACY_TIME_RANGE_MAX_RETRIES_PER_PAGE`.
- Expired responses still log/fail with the original payload and skip the final completed update.
- Empty pages still mark the page processed, set reached-end, and complete with the existing stats.
- Non-empty pages still filter/store/log/update cursor/run before-start logic via the existing
  non-empty-page helper.
- Inner-loop task-stop checks, max-retry failure logs, outer-stop completion, fetch call shape,
  initial cursor formatting, default and explicit `perPage`, invalid timestamp fallback,
  before-start stopping, public API behavior, task status semantics, schema/config behavior,
  official MCP HTTP behavior, and cookie-based crawler behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction focused retry, max-retry, expired, empty-page, filtered-page, before-start, and
  outer-stop tests passed.
- The same focused tests passed after extracting the page helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 legacy time-range run helper

Changed:

- Reused existing time-range and legacy time-range characterization coverage for time-bound
  resolution, default `perPage`, outer-stop completion, filtered page import, invalid oldest
  timestamp cursor fallback, out-of-range pages, before-start termination, retryable fetch
  failures, max-retry termination, expired responses, and empty pages.
- Added `_LegacyTimeRangeRunResult` and `_run_legacy_time_range_pages` in
  `backend/services/crawl_service.py`.
- Moved the legacy time-range outer page loop out of `run_crawl_time_range_task`, leaving the
  entrypoint responsible for time parsing, running-state/log initialization, official-vs-legacy
  dispatch, crawler preparation, expired early return, final completion update, exception handling,
  and crawler unregister cleanup.

Behavior impact:

- Intended behavior change: none.
- The legacy page loop still uses the same default/explicit `perPage`, initial cursor formatting,
  max-retry limit, page processing helper, task-stop check, page-failure handling, finish condition,
  expired-response early return, and final stats object.
- Expired responses still fail the task inside the existing expired helper and skip the final
  completed update.
- Outer-stop completion, empty-page completion, retry failure termination, filtered import stats,
  invalid cursor fallback, before-start stopping, public API behavior, task status semantics,
  schema/config behavior, official MCP HTTP behavior, and cookie-based crawler behavior are
  unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_resolve_time_range_uses_last_days_and_swaps_reversed_bounds tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_uses_default_per_page_when_missing tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_filters_topics_and_advances_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_keeps_invalid_oldest_time_as_next_end_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_counts_unstored_out_of_range_page tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_when_page_is_before_start_time tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_retries_failed_page_fetch tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_stops_after_max_failed_page_fetches tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_expired_response_fails_with_original_payload tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_time_range_crawl_stops_after_empty_page -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction focused time-range and legacy time-range tests passed.
- The same focused tests passed after extracting the run helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 45 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 761 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official topic page fetch helper

Changed:

- Reused existing official crawl route/helper coverage, then added characterization coverage for
  the official page fetch helper call shape and payload-topic extraction.
- Added `_OfficialTopicPage` and `_fetch_official_topic_page` in
  `backend/services/crawl_service.py`.
- Reused the helper from both official time-range crawling and the shared official page crawling
  loop, so the `get_group_topics(group_id, limit=per_page, scope="all", end_time=cursor)` call
  shape and `official_payload_topics` parsing now live in one place.

Behavior impact:

- Intended behavior change: none.
- Official latest, incremental, historical, all, and time-range flows still use the same client
  construction, per-page cap, cursor value, `scope="all"`, empty-page termination, duplicate
  accounting, latest-mode existing-topic filtering, import stats, completion messages, and
  time-range filtering.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_fetch_official_topic_page_preserves_call_shape_and_payload_topics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_next_page_cursor_requires_has_more_and_moving_cursor tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_pages_remaining_preserves_unbounded_and_limit_semantics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_per_page_limit_preserves_default_and_cap tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_filter_official_topics_by_time_range_preserves_bounds_and_oldest_time -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 45 tests passed.
- Focused official helper/page tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 46 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 762 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official empty page helper

Changed:

- Reused existing official crawl route/helper coverage, then added characterization coverage for
  official empty-page truthiness and log behavior.
- Added `_official_topic_page_empty` in `backend/services/crawl_service.py`.
- Reused the helper from both official time-range crawling and the shared official page crawling
  loop, keeping the existing `📭 无更多数据，任务结束` log message in one place.

Behavior impact:

- Intended behavior change: none.
- Official empty pages still log `📭 无更多数据，任务结束` exactly once and terminate the current
  page loop.
- Non-empty official pages still continue without logging the empty-page message.
- Official latest, incremental, historical, all, and time-range flows still use the same client
  construction, page fetch shape, per-page cap, cursor handling, duplicate accounting, latest-mode
  existing-topic filtering, import stats, completion messages, and time-range filtering.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topic_page_empty_preserves_log_and_truthiness tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_fetch_official_topic_page_preserves_call_shape_and_payload_topics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_next_page_cursor_requires_has_more_and_moving_cursor tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_pages_remaining_preserves_unbounded_and_limit_semantics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_filter_official_topics_by_time_range_preserves_bounds_and_oldest_time -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 46 tests passed.
- Focused official empty-page/page helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 47 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 763 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official next cursor helper

Changed:

- Reused existing official crawl route/helper coverage, then added characterization coverage for
  official next-cursor continuation and end-of-pagination log behavior.
- Added `_official_next_cursor_or_log_end` in `backend/services/crawl_service.py`.
- Reused the helper from both official time-range crawling and the shared official page crawling
  loop, keeping the existing `✅ 官方分页已无更多数据` log message in one place.

Behavior impact:

- Intended behavior change: none.
- Official pages with a moving next cursor still continue with that cursor and do not log the
  pagination-end message.
- Official pages without `has_more`, without a usable next cursor, or with a non-moving cursor still
  log `✅ 官方分页已无更多数据` and terminate the current page loop.
- Official latest, incremental, historical, all, and time-range flows still use the same client
  construction, page fetch shape, empty-page handling, per-page cap, cursor handling, duplicate
  accounting, latest-mode existing-topic filtering, import stats, completion messages, and
  time-range filtering.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_next_cursor_or_log_end_preserves_cursor_and_end_log tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_next_page_cursor_requires_has_more_and_moving_cursor tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topic_page_empty_preserves_log_and_truthiness tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_fetch_official_topic_page_preserves_call_shape_and_payload_topics -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 47 tests passed.
- Focused official next-cursor/page helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 48 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 764 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official topic client helper

Changed:

- Reused existing official crawl route/client coverage, then added characterization coverage for
  official client construction and task-log callback binding.
- Added `_official_topic_client` in `backend/services/crawl_service.py`.
- Reused the helper from both official time-range crawling and the shared official page crawling
  loop, keeping `OfficialTopicClient(log_callback=lambda message: add_task_log(task_id, message))`
  behavior in one place.

Behavior impact:

- Intended behavior change: none.
- Official client construction still creates a fresh `OfficialTopicClient` per official task runner.
- Official client log callbacks still forward each client log message to `add_task_log` with the
  original `task_id`.
- Official latest, incremental, historical, all, and time-range flows still use the same client
  construction timing, database construction timing, page fetch shape, empty-page handling,
  per-page cap, cursor handling, duplicate accounting, latest-mode existing-topic filtering,
  import stats, completion messages, and time-range filtering.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topic_client_preserves_log_callback_binding tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_fetch_official_topic_page_preserves_call_shape_and_payload_topics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_next_cursor_or_log_end_preserves_cursor_and_end_log -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 48 tests passed.
- Pre-extraction `tests.test_official_topic_client_helpers`: 16 tests passed.
- Focused official client/page/cursor helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 49 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 765 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official topics-to-import helper

Changed:

- Reused existing official crawl route/helper coverage, then added characterization coverage for
  latest-mode topic selection and non-latest page logging.
- Added `_official_topics_to_import_for_mode` in `backend/services/crawl_service.py`.
- Reused the helper from the shared official page crawling loop, keeping latest-mode existing-topic
  checks, page-analysis logs, no-new-topic stop behavior, and non-latest page logs in one place.

Behavior impact:

- Intended behavior change: none.
- Official latest mode still checks existing topics before import, logs `📊 官方页面分析: ...`,
  stops before import when all topics already exist, and logs `✅ 本页话题均已存在，最新采集完成`.
- Official non-latest modes still import all deduplicated page topics and log `📄 官方本页获取 ...`.
- Official time-range crawling is unchanged and does not use this helper.
- Official latest, incremental, historical, and all flows still use the same client construction,
  database construction timing, page fetch shape, empty-page handling, per-page cap, cursor
  handling, duplicate accounting, import stats, completion messages, and oldest-cursor behavior.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.
- Unrelated dirty downloader files were left outside this P4 slice; a minimal unstaged
  syntax/test-precondition repair was needed there to restore current-worktree testability.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topics_to_import_for_mode_preserves_latest_and_page_logs tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_new_official_topics_preserves_existing_check_order_and_missing_id_semantics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_latest_branch_skips_legacy_crawler -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 49 tests passed.
- Pre-extraction `tests.test_official_topic_client_helpers`: 16 tests passed.
- Focused official topic-selection/latest helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 50 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- Full backend unittest discovery: 766 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official import page helper

Changed:

- Reused existing official crawl route/helper coverage, then added characterization coverage for
  the import-then-accumulate page stats order.
- Added `_official_import_page_topics` in `backend/services/crawl_service.py`.
- Reused the helper from both official time-range crawling and the shared official page crawling
  loop, keeping page import and total-stat accumulation in one place.

Behavior impact:

- Intended behavior change: none.
- Official page import still calls `_official_import_topics` with the same database, official
  client, group ID, topic list, and task ID arguments.
- Official total stats still accumulate only after `_official_import_topics` returns page stats.
- The helper returns the original page stats for characterization and future local inspection, but
  both official loops continue to ignore that return value as before.
- Official latest, incremental, historical, all, and time-range flows still use the same client
  construction, database construction timing, page fetch shape, empty-page handling, per-page cap,
  cursor handling, duplicate accounting, latest-mode existing-topic filtering, import stats,
  completion messages, and oldest-cursor behavior.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.
- Unrelated dirty downloader files and scripts were left outside this P4 slice; minimal unstaged
  syntax/test-precondition repairs were needed there to restore current-worktree testability.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_import_page_topics_preserves_import_then_accumulate_order tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_import_topics_preserves_comment_count_stats_and_commit tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_topics_to_import_for_mode_preserves_latest_and_page_logs -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 50 tests passed after restoring unrelated
  dirty downloader syntax.
- Pre-extraction `tests.test_official_topic_client_helpers`: 16 tests passed.
- Focused official import-page helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 51 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 90 tests passed after unstaged dirty-file testability
  repair.
- Full backend unittest discovery: 767 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 shared stopped-with-log helper

Changed:

- Reused existing official/legacy crawl route coverage, then added characterization coverage for
  the shared stopped-task log helper.
- Renamed `_legacy_time_range_task_stopped` to `_task_stopped_with_log` in
  `backend/services/crawl_service.py`.
- Reused the helper from legacy time-range crawling and both official crawling loops, keeping the
  existing `🛑 任务已停止` log in one place.

Behavior impact:

- Intended behavior change: none.
- Stopped tasks still call `is_task_stopped(task_id)` once per check.
- Non-stopped tasks still return `False` without logging.
- Stopped tasks still log `🛑 任务已停止` and return `True`.
- Legacy time-range crawling and official time-range/page crawling still break out of the current
  loop at the same stop-check point as before.
- Official latest, incremental, historical, all, and time-range flows still use the same client
  construction, database construction timing, page fetch shape, empty-page handling, per-page cap,
  cursor handling, duplicate accounting, latest-mode existing-topic filtering, import stats,
  completion messages, and oldest-cursor behavior.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.
- Unrelated dirty downloader files and scripts were left outside this P4 slice; their unstaged
  testability repairs remained unstaged.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_task_stopped_with_log_preserves_stop_log_semantics tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_legacy_time_range_outer_stop_completes_without_fetching tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_latest_branch_skips_legacy_crawler -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 51 tests passed.
- Pre-extraction `tests.test_official_topic_client_helpers`: 16 tests passed.
- Focused shared stop-helper tests passed after helper rename/reuse.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 52 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 90 tests passed.
- Full backend unittest discovery: 768 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official group oldest cursor helper

Changed:

- Reused existing official branch coverage, then added characterization coverage for group-scoped
  oldest-cursor database construction and `allow_empty` forwarding.
- Added `_official_start_cursor_for_group_oldest` in `backend/services/crawl_service.py`.
- Reused the helper from official incremental-from-oldest and official all-from-oldest entrypoints,
  keeping `ZSXQDatabase(group_id)` construction and `_official_start_cursor_from_oldest(...,
  allow_empty=...)` call shape in one place.

Behavior impact:

- Intended behavior change: none.
- Official incremental-from-oldest still constructs `ZSXQDatabase(group_id)`, calls
  `_official_start_cursor_from_oldest(..., allow_empty=False)`, fails with the same empty-database
  message when the start cursor is `""`, and otherwise calls `_run_official_crawl_pages_task` with
  mode `incremental`.
- Official all-from-oldest still constructs `ZSXQDatabase(group_id)`, calls
  `_official_start_cursor_from_oldest(..., allow_empty=True)`, and calls
  `_run_official_crawl_pages_task` with mode `all`, unbounded pages, and per-page `20`.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.
- Unrelated dirty downloader files and scripts were left outside this P4 slice.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_start_cursor_for_group_oldest_preserves_db_construction_and_allow_empty tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_all_branch_uses_oldest_cursor_and_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_incremental_branch_uses_oldest_cursor_and_skips_legacy_crawler tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_official_incremental_empty_database_fails_without_legacy_crawler -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 52 tests passed.
- Pre-extraction `tests.test_official_topic_client_helpers`: 16 tests passed.
- Focused official oldest-cursor helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 53 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 90 tests passed.
- Full backend unittest discovery: 769 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 official unique page helper

Changed:

- Reused existing official crawl helper coverage, then added characterization coverage for the
  composed official page fetch, empty-page log, and per-run duplicate tracking semantics.
- Added `_OfficialUniqueTopicPage` and `_fetch_unique_official_topic_page` in
  `backend/services/crawl_service.py`.
- Reused the helper from official time-range and page-count crawl loops, keeping raw page topics
  available for existing time-range logs while passing deduplicated topics to filtering/import logic.

Behavior impact:

- Intended behavior change: none.
- Official page fetch still calls `OfficialTopicClient.get_group_topics` with the same group,
  `limit`, `scope="all"`, and `end_time` arguments.
- Empty official pages still emit `📭 无更多数据，任务结束` and stop the loop before dedupe/import.
- Duplicate topic tracking still increments `total_stats["duplicates"]` before filtering/import and
  preserves the same `seen_topic_ids` semantics.
- Official time-range logs still count raw page topics, while filtering still receives deduplicated
  topics.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are unchanged.
- No legacy/fallback behavior was removed.
- Unrelated dirty downloader files and scripts were left outside this P4 slice.

Verification:

```powershell
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m py_compile backend\services\crawl_service.py tests\test_crawl_routes_helpers.py
uv run python -m unittest tests.test_crawl_routes_helpers.CrawlRoutesHelperTests.test_fetch_unique_official_topic_page_preserves_empty_and_dedupe_semantics -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest tests.test_official_topic_client_helpers -v
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_crawl_routes_helpers`: 53 tests passed.
- Pre-extraction `tests.test_official_topic_client_helpers`: 16 tests passed.
- Focused official unique-page helper test passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_crawl_routes_helpers`: 54 tests passed.
- `tests.test_official_topic_client_helpers`: 16 tests passed.
- `tests.test_zsxq_file_downloader_helpers`: 90 tests passed.
- Full backend unittest discovery: 770 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 topic pagination timestamp offset reuse

Changed:

- Reused existing `_offset_zsxq_end_time` coverage before editing
  `backend/crawlers/topic_pagination.py`.
- Replaced duplicated inline timestamp-minus-milliseconds formatting in legacy historical,
  all-historical, and incremental pagination paths with `_offset_zsxq_end_time`.
- Left `crawl_latest_until_complete` retry timestamp handling unchanged because that branch has a
  different legacy import/exception shape and replacing it could change failure behavior.

Behavior impact:

- Intended behavior change: none.
- The reused helper performs the same `+0800` parsing, millisecond subtraction, and `+0800`
  formatting as the removed inline blocks.
- Existing log messages, retry counters, fallback exception handling, one-hour skip behavior,
  pagination stop conditions, database reads/writes, and return shapes are unchanged.
- No legacy/fallback behavior was removed.
- Unrelated dirty downloader files and scripts were left outside this P4 slice.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m py_compile backend\crawlers\topic_pagination.py tests\test_zsxq_interactive_crawler_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_zsxq_interactive_crawler_helpers`: 4 tests passed.
- Focused pagination helper tests passed after reuse.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_zsxq_interactive_crawler_helpers`: 4 tests passed.
- `tests.test_crawl_routes_helpers`: 54 tests passed.
- Full backend unittest discovery: 770 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 topic pagination hour offset helper

Changed:

- Reused existing topic pagination helper tests before editing `backend/crawlers/topic_pagination.py`.
- Added `_format_offset_zsxq_end_time` and `_offset_zsxq_end_time_by_hours` so millisecond and
  hour offsets share the same ZSXQ timestamp parsing/formatting path.
- Replaced three duplicated legacy page-failure one-hour skip blocks with
  `_offset_zsxq_end_time_by_hours(end_time, 1)`.
- Added characterization coverage for the hour-offset helper's `+0800` output format.

Behavior impact:

- Intended behavior change: none against the original legacy skip semantics.
- The one-hour skip branches still subtract exactly one hour, preserve the `+0800` no-colon
  timestamp format, keep the same log messages, and keep the same fallback exception logging.
- This also removes a hidden dependency on inline `datetime/timedelta` imports in adjacent retry
  code, keeping the max-retry skip path equivalent after the previous timestamp-helper reuse.
- `crawl_latest_until_complete` timestamp retry logic was left unchanged because it has a different
  legacy branch shape and was not part of this safe slice.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are otherwise unchanged.
- No legacy/fallback behavior was removed.
- Existing dirty downloader risk-log files and scripts were inspected but left outside this P4
  slice because they add new CLI/logging behavior.

Verification:

```powershell
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m py_compile backend\crawlers\topic_pagination.py tests\test_zsxq_interactive_crawler_helpers.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Pre-extraction `tests.test_zsxq_interactive_crawler_helpers`: 4 tests passed.
- Focused pagination helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_zsxq_interactive_crawler_helpers`: 5 tests passed.
- `tests.test_crawl_routes_helpers`: 54 tests passed.
- Full backend unittest discovery: 771 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 topic pagination latest retry offset reuse

Changed:

- Reused existing `_offset_zsxq_end_time` coverage before editing
  `backend/crawlers/topic_pagination.py`.
- Replaced the last inline millisecond timestamp-offset block in
  `crawl_latest_until_complete` retry handling with `_offset_zsxq_end_time`.
- Confirmed by grep that `topic_pagination.py` now keeps ZSXQ timestamp parsing/formatting in the
  shared offset helper path.

Behavior impact:

- Intended behavior change: none.
- The latest-record retry branch still subtracts `self.timestamp_offset_ms`, preserves the `+0800`
  no-colon timestamp format, keeps the same exception fallback log, and keeps the same retry/stop
  flow.
- Public API behavior, task status semantics, schema/config behavior, official MCP HTTP behavior,
  legacy cookie crawler behavior, and fallback behavior are otherwise unchanged.
- No legacy/fallback behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P4 slice.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\topic_pagination.py tests\test_zsxq_interactive_crawler_helpers.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
git grep -n -e "from datetime import datetime, timedelta" -e "dt = datetime.fromisoformat" -- backend/crawlers/topic_pagination.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused pagination helper tests passed after helper reuse.
- `py_compile` passed.
- Grep confirmed `topic_pagination.py` has no remaining inline datetime/timedelta offset block;
  the only `datetime.fromisoformat` match is inside the shared formatter helper.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_zsxq_interactive_crawler_helpers`: 5 tests passed.
- `tests.test_crawl_routes_helpers`: 54 tests passed.
- Full backend unittest discovery: 771 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 topic pagination retry constant

Changed:

- Reused existing topic pagination helper tests before editing `backend/crawlers/topic_pagination.py`.
- Added `TOPIC_PAGINATION_MAX_RETRIES_PER_PAGE = 10`.
- Replaced four duplicated local `max_retries_per_page = 10` assignments with the shared constant.
- Added characterization coverage for the current retry count.

Behavior impact:

- Intended behavior change: none.
- Historical, all-historical, incremental, and latest pagination paths still use 10 max retries per
  page.
- Retry loop bounds, retry log interpolation, max-retry skip/stop branches, stop checks, timestamp
  fallback behavior, return shapes, task status behavior, and crawler side effects are unchanged.
- Public API behavior, schema/config behavior, official MCP HTTP behavior, legacy cookie crawler
  behavior, and fallback behavior are otherwise unchanged.
- No legacy/fallback behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P4 slice.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\topic_pagination.py tests\test_zsxq_interactive_crawler_helpers.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
git grep -n "max_retries_per_page = 10" -- backend/crawlers/topic_pagination.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused pagination helper tests passed after constant extraction.
- `py_compile` passed.
- Grep found no remaining local `max_retries_per_page = 10` assignments in
  `topic_pagination.py`.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_zsxq_interactive_crawler_helpers`: 6 tests passed.
- `tests.test_crawl_routes_helpers`: 54 tests passed.
- Full backend unittest discovery: 772 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P4 topic pagination stats helper

Changed:

- Reused existing topic pagination helper tests before editing `backend/crawlers/topic_pagination.py`.
- Added `_empty_topic_pagination_stats`.
- Replaced four duplicated pagination stats initializers with the shared helper.
- Added characterization coverage for the stats shape and independent dict instances.

Behavior impact:

- Intended behavior change: none.
- Historical, all-historical, incremental, and latest pagination paths still initialize
  `new_topics`, `updated_topics`, `errors`, and `pages` to zero.
- Each crawl run still receives a fresh mutable stats dict; no stats state is shared across runs.
- Retry logic, stop checks, timestamp fallback behavior, return shapes, task status behavior, and
  crawler side effects are unchanged.
- Public API behavior, schema/config behavior, official MCP HTTP behavior, legacy cookie crawler
  behavior, and fallback behavior are otherwise unchanged.
- No legacy/fallback behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P4 slice.

Verification:

```powershell
uv run python -m py_compile backend\crawlers\topic_pagination.py tests\test_zsxq_interactive_crawler_helpers.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
git grep -n "total_stats = {'new_topics': 0, 'updated_topics': 0, 'errors': 0, 'pages': 0}" -- backend/crawlers/topic_pagination.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_zsxq_interactive_crawler_helpers -v
uv run python -m unittest tests.test_crawl_routes_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused pagination helper tests passed after helper extraction.
- `py_compile` passed.
- Grep found no remaining inline pagination stats initializer in `topic_pagination.py`.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_zsxq_interactive_crawler_helpers`: 7 tests passed.
- `tests.test_crawl_routes_helpers`: 54 tests passed.
- Full backend unittest discovery: 773 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-12 - P3 column scope group helper

Changed:

- Reused existing column database helper tests before editing
  `backend/storage/zsxq_columns_database.py`.
- Added `ZSXQColumnsDatabase._scope_group_id_param`.
- Replaced seven duplicated `group_id if group_id is not None else self.group_id` scope
  normalizations in column/topic detail read paths with the instance helper.
- Added characterization coverage for explicit group ID precedence, instance group fallback, numeric
  string coercion, and blank-group unscoped behavior.

Behavior impact:

- Intended behavior change: none.
- `get_column`, `get_column_topics`, `get_topic_detail`, `get_topic_images`, `get_topic_files`,
  `get_topic_videos`, and `get_topic_comments` still use explicit `group_id` when provided and fall
  back to `self.group_id` only when the argument is `None`.
- Existing `_scope_group_id_param` coercion behavior is preserved: numeric strings become ints, blank
  values become `None`, and query helper SQL/params stay unchanged.
- Public API behavior, PostgreSQL schema behavior, query result shapes, commit behavior, legacy/fallback
  behavior, and task behavior are unchanged.
- Existing dirty downloader risk-log files and scripts remain outside this P3 slice.

Verification:

```powershell
uv run python -m py_compile backend\storage\zsxq_columns_database.py tests\test_zsxq_columns_database_helpers.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
git grep -n "scope_group_id = _scope_group_id_param(group_id if group_id is not None else self.group_id)" -- backend/storage/zsxq_columns_database.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest tests.test_zsxq_columns_database_helpers -v
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused column database helper tests passed after helper extraction.
- `py_compile` passed.
- Grep found no remaining duplicated column scope normalization expression.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- `tests.test_zsxq_columns_database_helpers`: 71 tests passed.
- Full backend unittest discovery: 774 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 account cookie value helper

Changed:

- Added characterization coverage for account cookie resolution in `tests/test_account_context.py`.
- Covered database account cookie precedence, whitespace trimming, config fallback, placeholder config
  rejection, group cookie precedence, and group-to-primary fallback.
- Added `backend.core.account_context._account_cookie_value`.
- Replaced duplicated account-cookie extraction in `get_primary_cookie` and `get_cookie_for_group`.

Behavior impact:

- Intended behavior change: none.
- Public API behavior is unchanged: both functions still return stripped non-empty cookies or `None`.
- Fallback order is unchanged: primary cookie prefers the first SQL account before config; group cookie
  prefers the group SQL account before primary cookie fallback.
- Error semantics are unchanged: SQL/config lookup failures are still swallowed exactly at the existing
  try/except boundaries.
- Existing config placeholder handling remains unchanged: `your_cookie_here` is ignored.
- No schema, task, route, crawler, legacy, or fallback-removal behavior changed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_account_context -v
uv run python -m py_compile backend\core\account_context.py tests\test_account_context.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Characterization tests passed before production code changes.
- Focused account context tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 779 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 account summary value helper

Changed:

- Added characterization coverage for account summary fallback/cache behavior in
  `tests/test_account_context.py`.
- Covered SQL summary precedence, first-account summary fallback, missing account skip behavior, and
  `build_account_group_detection` cache reuse.
- Added `backend.core.account_context._account_summary_value`.
- Replaced duplicated four-field account summary payload construction in
  `get_account_summary_for_group_auto` and `build_account_group_detection`.

Behavior impact:

- Intended behavior change: none.
- Public API response shapes are unchanged: account summaries still expose only `id`, `name`,
  `created_at`, and `cookie` in the existing order.
- SQL summary precedence remains unchanged; the existing SQL summary object is still returned directly.
- First-account fallback still uses `get_first_account(mask_cookie=True)`.
- Group detection still calls `get_account_by_id(account_id, mask_cookie=True)`, skips missing
  accounts, stringifies group IDs, and caches the resulting mapping.
- Existing SQL/config exception swallowing and config fallback behavior are unchanged.
- No schema, task, route, crawler, legacy, or fallback-removal behavior changed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_account_context -v
uv run python -m py_compile backend\core\account_context.py tests\test_account_context.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Characterization tests passed before production code changes.
- Focused account context tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 782 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 account self route wrapper

Changed:

- Added characterization coverage for the four account self endpoints in
  `tests/test_account_routes_helpers.py`.
- Locked existing network-error status/details and generic-error status/details for account and group
  self read/refresh endpoints.
- Added `backend.routes.account_routes._run_self_response_route`.
- Replaced four duplicated `asyncio.to_thread` plus exception-wrapper blocks with the shared helper.

Behavior impact:

- Intended behavior change: none.
- Public route paths, HTTP methods, response payloads, helper call order, and `asyncio.to_thread`
  offloading behavior are unchanged.
- `HTTPException` is still re-raised without wrapping.
- `requests.RequestException` still maps to HTTP 502 with the same English or Chinese message prefix.
- Other exceptions still map to HTTP 500 with the same endpoint-specific message prefix.
- No schema, task, crawler, storage, legacy, or fallback-removal behavior changed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_account_routes_helpers -v
uv run python -m py_compile backend\routes\account_routes.py tests\test_account_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Characterization tests passed before production code changes.
- Focused account route helper tests passed after wrapper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 784 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 task stream payload helpers

Changed:

- Added `backend.routes.task_routes._task_log_payload`, `_task_removed_payload`, and
  `_task_heartbeat_payload`.
- Replaced repeated SSE stream payload literals for log, removed-task, and heartbeat events.
- Added helper coverage in `tests/test_task_routes_helpers.py` for the extracted payload shapes and
  the existing removed-task Chinese message.

Behavior impact:

- Intended behavior change: none.
- SSE frame formatting remains owned by `_sse_event` and is unchanged.
- Stream ordering, subscription lifecycle, polling timeout, drain behavior, task status payloads, and
  terminal-task break conditions are unchanged.
- Existing public task route paths, response payloads, status codes, and cleanup behavior are unchanged.
- No schema, crawler, storage, legacy, or fallback-removal behavior changed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m py_compile backend\routes\task_routes.py tests\test_task_routes_helpers.py
uv run python -m unittest tests.test_task_routes_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused task route helper tests passed after payload helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 785 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 config cookie mask helper

Changed:

- Added `backend.routes.core_routes._masked_config_cookie`.
- Replaced inline config-cookie masking in `get_config` with the helper.
- Added helper coverage in `tests/test_core_routes_helpers.py` for empty, placeholder, and configured
  cookie values.

Behavior impact:

- Intended behavior change: none.
- `GET /api/config` still reports `auth.cookie` as `***` for any configured non-placeholder cookie.
- Empty cookies and the legacy placeholder `your_cookie_here` still report `未配置`.
- Public route path, response structure, config loading, configured detection, database/download
  payloads, and exception semantics are unchanged.
- No schema, crawler, storage, task, legacy, or fallback-removal behavior changed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m py_compile backend\routes\core_routes.py tests\test_core_routes_helpers.py
uv run python -m unittest tests.test_core_routes_helpers -v
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused core route helper tests passed after helper extraction.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 786 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 local media path helper

Changed:

- Added `backend.routes.media_routes._existing_local_media_path`.
- Reused it in the local image and local video endpoints for safe child path resolution and missing
  file checks.
- Added helper coverage in `tests/test_media_routes_helpers.py` for existing files, missing files,
  and parent-path escape attempts.

Behavior impact:

- Intended behavior change: none.
- Local image routes still resolve under `get_group_data_dir(group_id) / "images"` and return a
  byte `Response` with the same content-type fallback.
- Local video routes still resolve under `get_group_dir(group_id) / "column_videos"` and return the
  same `FileResponse` shape with filename and content-type fallback.
- Missing images still raise HTTP 404 with `图片不存在`; missing videos still raise HTTP 404 with
  `视频不存在`.
- Parent-path escapes still raise HTTP 403 with `禁止访问该路径`.
- No schema, crawler, storage, task, legacy, or fallback-removal behavior changed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_media_routes_helpers -v
uv run python -m py_compile backend\routes\media_routes.py tests\test_media_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing media route helper tests passed before production code changes.
- Focused media route helper tests passed after adding local media path coverage.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 789 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 local group fallback entry helper

Changed:

- Added `backend.routes.group_routes._build_local_group_entry_from_sources`.
- Moved the local-only group entry composition path into the helper: default fields, local
  `group_meta.json`, local database enrichment, and final entry construction.
- Added helper coverage in `tests/test_group_routes_helpers.py` to lock the meta-before-database
  fallback ordering.

Behavior impact:

- Intended behavior change: none.
- Official groups are still merged first, and groups present in both official and local sources
  still get the existing `source|local` marker and persisted local metadata.
- Local-only groups still use the same default fields, `group_meta.json` fields, SQLite-compatible
  local metadata reads, statistics fallback, sorted response order, and final response shape.
- No fallback, legacy, schema, crawler, storage, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_group_routes_helpers -v
uv run python -m py_compile backend\routes\group_routes.py tests\test_group_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing group route helper tests passed before production code changes.
- Focused group route helper tests passed after extracting the local fallback entry helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 790 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 topic page response helper

Changed:

- Added `backend.routes.topic_routes._build_topic_page_response`.
- Reused it in the all-topics and group-topics list response builders.
- Added helper coverage in `tests/test_topic_routes_helpers.py` for row formatting, pagination
  shape, and query/count execution order.

Behavior impact:

- Intended behavior change: none.
- Existing SQL builders, search parameters, ordering, count queries, row formatters, response field
  names, pagination calculation, database close behavior, and route wrappers are unchanged.
- The existing group search count-query behavior is preserved exactly; this slice only moves shared
  response composition after queries are built.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_topic_routes_helpers -v
uv run python -m py_compile backend\routes\topic_routes.py tests\test_topic_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing topic route helper tests passed before production code changes.
- Focused topic route helper tests passed after extracting the topic page response helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 791 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 daily task metadata helper

Changed:

- Added `backend.routes.daily_analysis_routes._daily_task_metadata`.
- Reused it in daily report task creation and daily crawl-plus-analysis task creation.
- Added helper coverage in `tests/test_daily_analysis_routes_helpers.py` for explicit report dates
  and the existing `None` default date value.

Behavior impact:

- Intended behavior change: none.
- Existing task types, task descriptions, metadata field names, `create_task` call order,
  `enqueue_runtime_task` call order, response payload shape, and task runner arguments are
  unchanged.
- Both daily analysis entrypoints still attach `group_id` and `report_date` metadata exactly as
  before.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_daily_analysis_routes_helpers -v
uv run python -m py_compile backend\routes\daily_analysis_routes.py tests\test_daily_analysis_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing daily analysis route helper tests passed before production code changes.
- Focused daily analysis route helper tests passed after extracting the task metadata helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 792 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 stock topic task response helper

Changed:

- Added `backend.routes.stock_topic_analysis_routes._create_stock_task_response`.
- Reused it in stock question, single stock-topic analysis, and batch stock-topic analysis task
  creation endpoints.
- Added helper coverage in `tests/test_stock_topic_analysis_routes_helpers.py` for task creation,
  enqueue order, metadata payload, and response shape.

Behavior impact:

- Intended behavior change: none.
- Existing request validation (`question 不能为空`, `stock_name 不能为空`, `stock_names 不能为空`),
  task types, task descriptions, metadata field names and values, batch normalization, runner
  functions, enqueue argument order, and response payload are unchanged.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_stock_topic_analysis_routes_helpers -v
uv run python -m py_compile backend\routes\stock_topic_analysis_routes.py tests\test_stock_topic_analysis_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing stock topic route helper tests passed before production code changes.
- Focused stock topic route helper tests passed after extracting the task response helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 793 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 daily stock concept task response helper

Changed:

- Added `backend.routes.daily_stock_concept_routes._stock_concept_task_metadata`.
- Added `backend.routes.daily_stock_concept_routes._create_daily_stock_concept_task_response`.
- Reused the helper in the daily stock concept task creation endpoint.
- Added helper coverage in `tests/test_daily_stock_concept_routes_helpers.py` for metadata
  defaults, task creation, enqueue order, and response shape.

Behavior impact:

- Intended behavior change: none.
- Existing task type, task description, metadata field names and values, task runner, enqueue
  argument order, error wrapper, and response payload are unchanged.
- The endpoint still accepts `background_tasks` for FastAPI compatibility even though this route
  uses `enqueue_runtime_task` directly, matching the prior behavior.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_daily_stock_concept_routes_helpers -v
uv run python -m py_compile backend\routes\daily_stock_concept_routes.py tests\test_daily_stock_concept_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing daily stock concept route helper tests passed before production code changes.
- Focused daily stock concept route helper tests passed after extracting the task response helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 A-share analysis task response helper

Changed:

- Added `backend.routes.a_share_routes.TASK_CREATED_MESSAGE`.
- Added `backend.routes.a_share_routes._a_share_task_metadata`.
- Added `backend.routes.a_share_routes._create_a_share_analysis_task_response`.
- Reused the helper in the A-share analysis task creation endpoint.
- Added helper coverage in `tests/test_a_share_routes_helpers.py` for global/group metadata, task
  creation, enqueue order, and response shape.

Behavior impact:

- Intended behavior change: none.
- Existing OpenAI API key preflight check, group normalization, date-range validation, task type,
  task description, metadata keyword argument, task runner, enqueue argument order, error wrappers,
  and response payload are unchanged.
- The task-created message literal was moved into a module constant with the same value.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_a_share_routes_helpers -v
uv run python -m py_compile backend\routes\a_share_routes.py tests\test_a_share_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Existing A-share route helper tests passed before production code changes.
- Focused A-share route helper tests passed after extracting the task response helper.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 797 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 core route dead helper cleanup

Changed:

- Removed `backend.routes.core_routes._add_table_counts`.
- Removed `backend.routes.core_routes._merge_timestamp_info`.
- Removed the tests that only existed to cover those now-unreferenced private helpers.
- Removed unused `os`, `List`, and `Optional` imports from `backend.routes.core_routes`.

Behavior impact:

- Intended behavior change: none.
- `rg` showed both private helpers were referenced only by their definitions and their helper tests;
  no production route, service, storage, frontend, script, or document references remained.
- Existing database stats response behavior still comes directly from `ZSXQDatabase` and
  `ZSXQFileDatabase`; that route path was not changed.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
rg -n "\b_add_table_counts\b|\b_merge_timestamp_info\b|from typing import Any, Dict, List, Optional|\bos\b" backend\routes\core_routes.py tests\test_core_routes_helpers.py
uv run python -m unittest tests.test_core_routes_helpers -v
uv run python -m py_compile backend\routes\core_routes.py tests\test_core_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused core route helper tests passed after removing unreferenced helpers.
- `py_compile` passed.
- `rg` found no remaining references to the removed helper names or removed imports in the edited
  files.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P3 columns fetch helper parameter cleanup

Changed:

- Removed the unused `background_tasks` parameter from
  `backend.routes.columns_routes._create_columns_fetch_task_response`.
- Updated the internal `fetch_group_columns` call site and focused helper tests.

Behavior impact:

- Intended behavior change: none.
- The public FastAPI route signature for `fetch_group_columns` still accepts `background_tasks`.
- The helper still creates the same ingestion task, sets the same running status, enqueues the
  same task runner with the same arguments, and returns the same response payload.
- Existing focused tests already asserted that no `BackgroundTasks.add_task` callback is scheduled;
  that behavior remains unchanged.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P3 slice.

Verification:

```powershell
uv run python -m unittest tests.test_columns_routes_helpers -v
uv run python -m py_compile backend\routes\columns_routes.py tests\test_columns_routes_helpers.py
rg -n "_create_columns_fetch_task_response\(" backend\routes\columns_routes.py tests\test_columns_routes_helpers.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused columns route helper tests passed after removing the unused private helper parameter.
- `py_compile` passed.
- `rg` showed only the helper definition, route call site, and updated tests reference the helper.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P3 columns route summary import cleanup

Changed:

- Removed unused `columns_fetch_summary` helper imports from
  `backend.routes.columns_routes`.
- Updated the focused route helper test to import `resolve_columns_fetch_config` directly from
  `backend.services.columns_fetch_summary` instead of through the route module.

Behavior impact:

- Intended behavior change: none.
- The route module did not call `_build_columns_fetch_result`, `_build_columns_progress_message`,
  or `_resolve_columns_fetch_config`; the aliases only acted as historical test coupling.
- Existing columns fetch task creation, route signatures, status update, enqueue behavior, response
  payloads, and service config resolver behavior are unchanged.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P3 slice.

Verification:

```powershell
uv run python -m unittest tests.test_columns_routes_helpers tests.test_columns_fetch_summary -v
uv run python -m py_compile backend\routes\columns_routes.py tests\test_columns_routes_helpers.py
rg -n "_build_columns_fetch_result|_build_columns_progress_message|_resolve_columns_fetch_config|resolve_columns_fetch_config" backend\routes\columns_routes.py tests\test_columns_routes_helpers.py tests\test_columns_fetch_summary.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Focused columns route and summary tests passed after removing the unused route aliases.
- `py_compile` passed.
- `rg` confirmed the route module no longer imports or exposes the removed summary helper aliases.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 service unused typing import cleanup

Changed:

- Removed unused `Any` from `backend.services.a_share_analysis_local_store`.
- Removed unused `List` from `backend.services.columns_comment_service`.

Behavior impact:

- Intended behavior change: none.
- Only unused typing imports were removed; function bodies, signatures, route behavior, response
  payloads, fallback behavior, file paths, logging, and persistence behavior are unchanged.
- `rg` and AST import-use scan showed these names were not used by the edited modules.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_columns_comment_service tests.test_a_share_analysis_service_helpers -v
uv run python -m py_compile backend\services\a_share_analysis_local_store.py backend\services\columns_comment_service.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Baseline focused service tests passed before removing the unused typing imports.
- Focused service tests passed after the import cleanup.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 A-share service unused Mapping import cleanup

Changed:

- Removed unused `Mapping` from `backend.services.a_share_analysis_service`.

Behavior impact:

- Intended behavior change: none.
- Only an unused typing import was removed; A-share analysis functions, prompts, fallback local
  storage behavior, database storage behavior, routes, scripts, response payloads, and logging are
  unchanged.
- `rg` confirmed no tests, scripts, docs, or backend modules import `Mapping` from
  `backend.services.a_share_analysis_service`; other `Mapping` usages import it directly from
  `typing`.
- Existing compatibility re-exports from `backend.services.a_share_analysis_service`, including
  parser helpers, `validate_day`, and group local-storage constants, were intentionally preserved.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_a_share_analysis_service_helpers -v
uv run python -m py_compile backend\services\a_share_analysis_service.py
rg -n "a_share_analysis_service import .*Mapping|\bMapping\b" backend\services\a_share_analysis_service.py tests scripts docs
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Baseline focused A-share analysis service tests passed before removing the unused typing import.
- Focused A-share analysis service tests passed after the import cleanup.
- `py_compile` passed.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

### 2026-06-13 - P2 topic route table constant import cleanup

Changed:

- Removed unused `GROUP_TOPIC_TABLES` and `TOPIC_DETAIL_TABLES` imports from
  `backend.routes.topic_routes`.
- Updated focused topic route helper tests to import those constants directly from
  `backend.services.topic_workflow_service`.

Behavior impact:

- Intended behavior change: none.
- Topic routes still call the same `_delete_single_topic_rows`, `_delete_group_topic_rows`, and
  `_clear_group_topic_data` helpers from `backend.services.topic_workflow_service`.
- The table constants remain defined in the workflow service and continue to drive the same delete
  order and deleted-count expectations.
- The route module no longer exposes those constants incidentally through historical test coupling.
- No schema, crawler, storage, fallback, legacy, route, or public response behavior was removed.
- Existing dirty downloader risk-log files and scripts remain outside this P2 slice.

Verification:

```powershell
uv run python -m unittest tests.test_topic_routes_helpers -v
uv run python -m py_compile backend\routes\topic_routes.py tests\test_topic_routes_helpers.py backend\services\topic_workflow_service.py
rg -n "GROUP_TOPIC_TABLES|TOPIC_DETAIL_TABLES|_delete_single_topic_rows|_delete_group_topic_rows" backend\routes\topic_routes.py tests\test_topic_routes_helpers.py backend\services\topic_workflow_service.py
uv run python scripts\scan_postgres_compat_debt.py
uv run python -m unittest discover -s tests
cmd.exe /d /c npm --prefix frontend run build
git diff --check
```

Result:

- Baseline focused topic route helper tests passed before removing the unused route imports.
- Focused topic route helper tests passed after the import cleanup.
- `py_compile` passed.
- `rg` confirmed the route module no longer imports the removed table constants and still calls
  the delete helpers used by production routes.
- PostgreSQL compatibility debt scan found no SQLite compatibility patterns.
- Full backend unittest discovery: 795 tests passed, 15 skipped.
- Frontend build passed, including Next.js lint/type checks.
- `git diff --check` passed with only Git's existing LF-to-CRLF working-copy warnings.

## Stop Conditions

Pause before editing if:

- New tracked changes appear in files targeted by the current slice.
- A test failure appears outside the edited area and is not clearly pre-existing.
- The slice requires route field, schema, prompt, task status, lock, retry, or config semantic
  changes.
- The implementation grows into a broad rewrite instead of a boundary-preserving extraction.
