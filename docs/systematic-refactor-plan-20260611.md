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

## Stop Conditions

Pause before editing if:

- New tracked changes appear in files targeted by the current slice.
- A test failure appears outside the edited area and is not clearly pre-existing.
- The slice requires route field, schema, prompt, task status, lock, retry, or config semantic
  changes.
- The implementation grows into a broad rewrite instead of a boundary-preserving extraction.
