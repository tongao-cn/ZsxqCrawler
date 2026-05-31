# File Download Failure Triage Plan

## Goal

Reduce frequent file download failures in the group file workflow by fixing concrete downloader failure modes without changing the product surface.

## Scope

- `backend/crawlers/zsxq_file_downloader.py`
- `tests/test_zsxq_file_downloader_helpers.py`
- `docs/file-download-failure-triage-plan.md`

## Constraints

- Keep the change backend-only and limited to file download behavior.
- Preserve current task creation, ingestion locks, database schema, and frontend API shape.
- Do not inspect or print secrets from local config.
- Leave unrelated dirty worktree changes untouched.

## Docs Checked

- `AGENTS.md`
- `README.md`
- `docs/project-architecture-roadmap.md`
- `docs/group_file_workbench_redesign_plan.md`

## Findings

- `download_file()` only read `file.id`, while raw Knowledge Planet file payloads and topic attachments commonly use `file_id`. Direct API-list download paths could therefore request `/v2/files/None/download_url`.
- The downloader retried while fetching the signed download URL, but did not retry the actual file body request after the signed URL was obtained.
- Recent persisted task history did not show file/download tasks in the latest task rows queried locally, so the code-path findings are currently stronger than runtime-log evidence.

## Execution Steps

1. Make `download_file()` accept both `id` and `file_id`, and fail early if neither exists.
2. Add a small retry loop around the file body download after a signed URL is acquired.
3. Add focused unit tests for `file_id` payload compatibility and retry-after-body-failure.
4. Run targeted downloader tests.

## Progress

- Made `download_file()` accept both `id` and `file_id`, with an early log/return when neither exists.
- Added a 3-attempt retry loop for the actual file body download after the signed URL is acquired.
- Added focused unit coverage for raw `file_id` payloads and body-download retry success.

## Changed Files

- `backend/crawlers/zsxq_file_downloader.py`
- `tests/test_zsxq_file_downloader_helpers.py`
- `docs/file-download-failure-triage-plan.md`

## Verification Results

- `uv run python -m pytest tests/test_zsxq_file_downloader_helpers.py`: failed because `pytest` is not installed in the local environment.
- `$env:PYTHONIOENCODING='utf-8'; uv run python -m unittest tests.test_zsxq_file_downloader_helpers`: passed.
