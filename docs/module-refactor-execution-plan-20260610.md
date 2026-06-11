# Module Refactor Execution Plan - 2026-06-10

## Purpose

This plan coordinates the next refactor rounds for the ZsxqCrawler module and page hotspots.
The goal is to avoid opportunistic "one slice at a time" work. Each slice should be selected
from this plan, verified with the listed commands, and committed as a coherent change.

## Current Baseline

Observed on 2026-06-10:

- Recent `main` commits added external stock summary API/export behavior:
  - `53abca3` Add recommendation windows to stock summary
  - `94db2df` Add stock summary export script
  - `97aee86` Add external stock summary API
- Current large-file hotspots:
  - `backend/crawlers/zsxq_file_downloader.py`: about 1334 lines
  - `backend/services/stock_topic_analysis_service.py`: about 989 lines
  - `backend/storage/zsxq_file_database.py`: about 639 lines
  - `frontend/src/components/DailyTopicAnalysisPanel.tsx`: about 251 lines
- The working tree contains untracked temporary stock-analysis scripts/results. They are out of
  scope for this plan unless cleanup is explicitly requested.

### Audit Refresh - 2026-06-11

Observed on 2026-06-11 before the next cleanup round:

- Current baseline verification passed:
  - `uv run python -m unittest discover -s tests`: 476 tests passed, 15 skipped.
  - `npm --prefix frontend run build`: passed.
  - `uv run python scripts\scan_postgres_compat_debt.py`: no SQLite compatibility patterns found.
- Recent `main` commits show that several earlier extraction slices have already landed:
  - `470292f` Extract downloader API retry helpers
  - `d6502a3` Extract stock analysis result builders
  - `7567650` Extract daily stock trend hook
  - `4c8f04d` Extract stock topic analysis panel hook
  - `54a3157` Handle terminal task status before unmount
- Current large-file hotspots from the 2026-06-11 scan:
  - `backend/storage/zsxq_database.py`: about 1425 lines
  - `backend/crawlers/zsxq_file_downloader.py`: about 1319 lines
  - `backend/storage/zsxq_columns_database.py`: about 1046 lines
  - `backend/services/stock_topic_analysis_service.py`: about 982 lines
  - `backend/services/file_workflow_service.py`: about 882 lines
  - `backend/services/a_share_analysis_service.py`: about 835 lines
  - `backend/services/tdx_a_share_export_service.py`: about 708 lines
  - `frontend/src/lib/api/types.ts`: about 640 lines
  - `frontend/src/app/groups/[groupId]/page.tsx`: about 446 lines
- Existing helper boundaries are active and should be extended rather than duplicated:
  - `backend/crawlers/zsxq_file_downloader_helpers.py`
  - `backend/services/stock_topic_analysis_helpers.py`
  - `backend/services/stock_topic_analysis_payloads.py`
  - `backend/storage/zsxq_file_database_helpers.py`
- The same untracked root-level `tmp_stock_analysis_*` files remain out of scope. Do not move,
  delete, stage, or reclassify them unless cleanup is explicitly requested.

## Systematic Refactor Backlog

Use this table to choose safe slices. Prefer lower-risk rows first unless a production bug points
elsewhere.

| Priority | Files or modules | Purpose | Behavior risk | Verification | New tests | Legacy, fallback, or compatibility handling |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Root `tmp_stock_analysis_*` files | Inventory only; do not clean by default | Low | `git status --short` | No | Preserve until the user explicitly asks for scratch cleanup |
| P1 | `backend/crawlers/zsxq_file_downloader.py`, `backend/crawlers/zsxq_file_downloader_helpers.py` | Continue extracting retry, response, and failure-classification helpers | Low to medium | `py_compile` plus downloader helper tests | Yes, characterization first | Preserve retry counts, sleeps, User-Agent rotation, `1030`, `1059`, and log semantics |
| P2 | `backend/services/stock_topic_analysis_service.py`, `backend/services/stock_topic_analysis_helpers.py`, `backend/services/stock_topic_analysis_payloads.py` | Move pure flow decisions and result builders out of orchestration | Low | stock topic service helper tests | Yes | Do not change prompts, AI output shape, checkpoint, rollback, or concurrency semantics |
| P3 | `backend/services/file_workflow_service.py` | Extract task failure/status/path helpers and reduce nested error handling | Medium | file route and workflow helper tests | Yes | Preserve task statuses, lock behavior, error messages, and side effects |
| P4 | `backend/storage/zsxq_file_database.py`, `backend/storage/zsxq_file_database_helpers.py` | Move payload and row mappers out of SQL methods | Medium | storage helper tests; PG smoke if SQL is touched | Yes | Do not change schema, `connect()`, `db_compat.py`, group-scope SQL, or runtime DDL behavior |
| P5 | `backend/routes/group_routes.py`, `backend/services/crawl_service.py`, `backend/crawlers/official_topic_client.py` | Document and narrow official-vs-legacy crawl fallback boundaries | Medium | group, crawl, and official topic tests | Maybe | Keep legacy crawler as an explicit source; do not delete fallback without reachability proof |
| P6 | `frontend/src/hooks/useTaskStatus.ts`, `frontend/src/components/TaskDock.tsx`, task list/log components | Consolidate SSE and fallback polling behavior | Medium | `npm --prefix frontend run build`; browser check for UI changes | Maybe | Preserve fallback polling and terminal-task handling semantics |
| P7 | `frontend/src/lib/api/types.ts`, `frontend/src/lib/api/*` | Split large API type surfaces only when callers remain compatible | Medium | `npm --prefix frontend run build` | Maybe | Keep `frontend/src/lib/api.ts` compatibility facade intact |
| P8 | `README.md`, `docs/project-architecture-roadmap.md`, active docs | Keep docs aligned with real module boundaries and verification commands | Low | grep references plus relevant builds/tests | No | Mark deprecated plans instead of deleting unless cleanup is in scope |

## Legacy And Fallback Register

Do not delete any item in this register during structural refactor slices. Each removal needs
separate proof: no references, unreachable runtime path, equivalent coverage, and a focused test.

| Area | Current role | Default action | Evidence or guardrail |
| --- | --- | --- | --- |
| Topic source `legacy` | Explicit cookie-based crawler path behind `topicSource=legacy` or legacy aliases | Keep | Route tests cover official path skipping legacy crawler and explicit legacy resolution |
| Official topic MCP path | Default topic crawl path when configured | Keep | `OfficialTopicClient` and crawl service tests cover source selection and import behavior |
| Group local fallback | Prevents frontend failure when official group lookup fails | Keep | `group_routes._build_group_info_fallback` tests cover fallback shape |
| A-share local CSV fallback | Allows A-share analysis to continue when PostgreSQL storage is unavailable | Keep | A-share tests cover local read/write fallback |
| `db_compat.py` | Narrow PostgreSQL connection and row-adaptation compatibility layer | Keep and avoid broad edits | Compatibility debt scan is clean; roadmap says no SQLite runtime behavior |
| File downloader retry fallback | Handles retryable HTTP/API failures and signed URL/download failures | Keep | Downloader helper tests cover retry decisions and failure classification |
| Task SSE fallback polling | Keeps frontend task status alive when SSE is unavailable or closes | Keep | `useTaskStatus` is a product behavior surface; build must pass after any changes |
| Tongdaxin official API adapter | Active A-share export path through TdxQuant APIs | Keep | Do not reintroduce `.blk` or `blocknew.cfg` paths |

## Behavior Locking Rules

Before modifying a hotspot, define the current behavior in tests or in an existing verified helper
test. Add characterization tests first when any of these are involved:

- public API fields or response status codes;
- task status, lock, cancellation, log, or terminal-state behavior;
- prompt text, AI output schema, model-routing values, or JSON parsing;
- PostgreSQL schema, SQL writes, group scoping, or runtime DDL policy;
- fallback paths for official topic crawl, local group data, A-share local files, downloader retry,
  or frontend task polling;
- empty values, malformed payloads, missing fields, duplicate IDs, invalid dates, or external
  dependency failures.

The test should lock current behavior. Do not change business logic just to make a new test pass.

## Operating Rules

1. Start each round by checking `git status --short` and recent commits.
2. Stage and commit only files changed for the current slice.
3. Do not modify untracked temporary analysis files unless explicitly asked.
4. Do not change PostgreSQL schema, runtime DDL behavior, prompt semantics, AI output schema, or
   public API fields in structural refactor slices.
5. Keep A-share recommendation, daily stock concepts, stock topic analysis, and file AI analysis as
   separate product workflows.
6. Prefer boundary-preserving extraction:
   - pure helpers before service orchestration changes;
   - payload/mapper helpers before storage write-path changes;
   - hooks before panel-level UI behavior changes;
   - tests before broader rewrites.
7. After every 2-3 commits, run full verification before continuing.

## Phase 0 - Baseline Freeze

### Goal

Confirm the current repo state and prevent accidental overlap with new or untracked work.

### Scope

- Read-only checks.
- No code changes.
- No commits.

### Commands

```powershell
git status --short
git log --oneline -10
git show --stat --oneline -3
```

### Exit Criteria

- Current dirty/untracked files are understood.
- Current recent commits are understood.
- The next implementation slice has a named file list and verification command.

## Phase 1 - File Downloader Retry And Response Handling

### Goal

Reduce duplicated retry and response logic in `backend/crawlers/zsxq_file_downloader.py` without
changing live HTTP behavior.

### Candidate Slices

1. Extract response logging decision:
   - helper: `should_log_full_response(attempt, max_retries, succeeded)`
   - callers: `fetch_file_list`, `get_download_url`
   - tests: first attempt, final attempt, success attempt

2. Extract API failure classification:
   - helper: `classify_api_failure(error_code, attempt, max_retries)`
   - expected categories:
     - `retry`
     - `non_retry`
     - `retry_exhausted`
     - `permission_denied_1030`
   - keep `1030` behavior scoped to download URL handling

3. Extract HTTP failure classification:
   - helper: `classify_http_failure(status_code, attempt, max_retries)`
   - preserve retryable status set: `429`, `500`, `502`, `503`, `504`

4. Only after the above helpers are stable, consider extracting small handler functions for:
   - JSON decode failure
   - retryable HTTP response
   - retryable API failure

### Non-Goals

- Do not change retry count.
- Do not change sleep intervals.
- Do not change User-Agent rotation.
- Do not change log text unless a test proves it is needed.
- Do not rewrite the whole request loop in one commit.

### Verification

```powershell
uv run python -m py_compile backend/crawlers/zsxq_file_downloader.py backend/crawlers/zsxq_file_downloader_helpers.py
uv run python -m unittest tests.test_zsxq_file_downloader_helpers -v
```

### Commit Boundary

One commit per helper family, for example:

- `Extract downloader response logging decision`
- `Extract downloader API failure classification`

## Phase 2 - Stock Topic Analysis Service Flow Helpers

### Goal

Keep `stock_topic_analysis_service.py` as orchestration and move pure flow calculations into
`stock_topic_analysis_helpers.py`.

### Candidate Slices

1. Extract processed-topic reconciliation:
   - inputs:
     - saved topic ids
     - current search result
     - skipped topic ids
   - outputs:
     - current topic ids
     - new topic ids
     - new skipped topic ids
     - merged processed topic ids
     - `has_new_processed_topic_ids`

2. Extract analysis mode decision:
   - possible results:
     - `up_to_date`
     - `initialize`
     - `incremental`
   - keep AI call decisions in the service until this helper has tests.

3. Extract small result builders:
   - empty search result with saved summary
   - empty search result without saved summary
   - completed result after AI summary
   - failed result after exception

### Non-Goals

- Do not change prompts.
- Do not change `MAX_BATCH_STOCKS` or image extraction cap text.
- Do not change stock-level concurrency semantics.
- Do not change database checkpoint or rollback behavior.
- Do not change public response fields.

### Verification

```powershell
uv run python -m py_compile backend/services/stock_topic_analysis_service.py backend/services/stock_topic_analysis_helpers.py
uv run python -m unittest tests.test_stock_topic_analysis_service_helpers -v
```

### Commit Boundary

One commit per behavior-neutral extraction, for example:

- `Extract stock topic progress reconciliation`
- `Extract stock topic analysis mode helpers`

## Phase 3 - External Stock Summary Review

### Goal

Review the newly added external stock summary API/export path before refactoring adjacent stock
topic code further.

### Target Files

- `backend/services/stock_external_summary_service.py`
- `backend/routes/stock_topic_analysis_routes.py`
- `scripts/export_external_stock_summary.py`
- related tests

### Review Questions

1. Does the route, service, and export script duplicate summary payload shaping?
2. Are recommendation windows defined in exactly one place?
3. Are export rows and API responses intentionally different?
4. Are docs and tests aligned with the actual API/export shape?

### Possible Slice

Extract shared payload helpers only if duplication is clear:

- candidate file: `backend/services/stock_external_summary_payloads.py`
- keep route and script behavior unchanged

### Verification

```powershell
uv run python -m unittest tests.test_stock_external_summary_service_helpers tests.test_export_external_stock_summary_script tests.test_stock_topic_analysis_routes_helpers -v
```

### Commit Boundary

Commit only if code changes are justified:

- `Extract external stock summary payload helpers`

## Phase 4 - File Database Payload Mappers

### Goal

Continue shrinking `backend/storage/zsxq_file_database.py` by moving pure payload and row mapping
logic into `backend/storage/zsxq_file_database_helpers.py`.

### Candidate Slices

1. Extract file/topic relation mapper.
2. Extract AI analysis insert/update parameter builder.
3. Extract import stats update logic.
4. Extract comment/content child payload mappers if tests already cover the SQL shape.

### Non-Goals

- Do not change table definitions.
- Do not change `connect()` or `db_compat`.
- Do not add runtime DDL.
- Do not change group-scope SQL behavior.

### Verification

```powershell
uv run python -m py_compile backend/storage/zsxq_file_database.py backend/storage/zsxq_file_database_helpers.py
uv run python -m unittest tests.test_zsxq_file_database_helpers -v
```

### Commit Boundary

- `Extract file database payload mappers`

## Phase 5 - Daily Topic Frontend Handler Hooks

### Goal

Keep `DailyTopicAnalysisPanel.tsx` focused on wiring views and task actions by moving async detail
state into hooks.

### Candidate Slices

1. Extract topic detail state:
   - selected topic id
   - loading state
   - stale request guard
   - open/close handlers

2. Extract stock trend detail state:
   - selected stock
   - 7-day trend loading
   - stale request guard
   - topic id aggregation per day

### Non-Goals

- Do not change UI styling.
- Do not change API request parameters.
- Do not add global pages.
- Do not change `/groups/[groupId]` as the primary group workbench.

### Verification

```powershell
npm --prefix frontend run build
```

### Commit Boundary

- `Extract daily topic detail hook`
- `Extract daily stock trend hook`

## Full Verification Gate

Run after any 2-3 commits, and always before closing a work round.

```powershell
uv run python -m unittest discover -s tests
npm --prefix frontend run build
git status --short
git log --oneline -8
```

## Stop Conditions

Pause and reassess before editing if any of these occur:

- New unrelated tracked changes appear in files targeted by the current phase.
- Tests fail outside the edited area and the failure is not clearly pre-existing.
- A slice requires changing prompt semantics, schema, route fields, or task behavior.
- The implementation would need a broad rewrite rather than a boundary-preserving extraction.
- Worktree state suggests another process or agent is writing the same files.

## Recommended Next Work Round

1. Phase 0 baseline freeze.
2. Phase 1 remaining slice: add or complete downloader HTTP failure classification only if the
   current request loops still duplicate that decision.
3. Add characterization tests for the exact downloader retry categories before editing loops.
4. Focused downloader verification and a narrow commit if code changed.
5. Phase 2 remaining slice: extract stock-topic analysis mode decision or another pure helper
   that does not touch prompts, AI calls, checkpointing, rollback, or public fields.
6. Focused stock topic verification and a narrow commit if code changed.
7. Reassess P3 file workflow helpers only after P1/P2 are complete or consciously skipped.
8. Full verification gate.
