# File Download Runtime Fix Plan

## Goal

Restore page-triggered file downloads after the current account cookie refresh.

## Scope

- Refresh the active local account cookie without echoing secret values.
- Verify the Knowledge Planet account state and one small real file download.
- Fix only the downloader status-write issue found during real download verification.

## Constraints

- Do not print, store in docs, or otherwise expose cookie values.
- Do not change frontend API shape, task runtime behavior, or PostgreSQL schema.
- Leave unrelated dirty worktree changes untouched.

## Docs Checked

- `AGENTS.md`
- `docs/project-architecture-roadmap.md`

## Findings

- The previous cookie returned `401 Unauthorized` for both `/v2/groups` and `/v2/files/{file_id}/download_url`.
- After refreshing the active account cookie, `/v2/groups` returned `200` with `succeeded=true`.
- A real small-file download fetched the file bytes successfully, then failed while writing `files.download_time`.
- PostgreSQL rejected `CASE WHEN ... THEN CURRENT_TIMESTAMP ELSE download_time END` because `download_time` is `TEXT`.

## Execution Steps

1. Update the active account cookie from clipboard.
2. Verify `/v2/groups`.
3. Reproduce one small real file download.
4. Cast `CURRENT_TIMESTAMP` to text in `update_file_download_status()`.
5. Run focused unit tests and retry the same real file download.

## Progress

- Active account cookie was refreshed.
- Account-state verification passed.
- Downloader status-write fix implemented.
- Real downloader verification passed for file `418584214288848`.
- Page-backed `download_single_file` worker path passed for file `415584854185218`.
- Signed download URLs are redacted from `get_download_url()` debug output.

## Changed Files

- `backend/storage/zsxq_file_database.py`
- `tests/test_zsxq_file_database_helpers.py`
- `docs/file-download-runtime-fix-plan.md`

## Verification Results

- `GET https://api.zsxq.com/v2/groups` with the refreshed local cookie returned `200` and `succeeded=true`.
- Real download for `418584214288848` returned `True`, changed status from `pending` to `completed`, and wrote a 7,509-byte local file.
- Worker-path download task for `415584854185218` completed successfully after one retry for API code `1059`, changed status from `pending` to `completed`, and wrote a 10,334-byte local file.
- `$env:PYTHONIOENCODING='utf-8'; uv run python -m unittest tests.test_zsxq_file_database_helpers tests.test_zsxq_file_downloader_helpers`: passed.
