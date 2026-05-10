# A-share Recommendation Pool Checkpoint Plan

## Goal

Make long-running A-share recommendation-pool analysis persist successful topic results during the run instead of waiting for the full task to finish.

## Scope

- PostgreSQL mode writes a checkpoint after every 20 successful topics and once more at task end.
- Each checkpoint writes topic stock extractions, daily mention deltas, and processed state in one transaction.
- File-only mode keeps the existing final CSV/state write behavior.
- No schema, frontend API, ranking formula, or daily stock-concept workflow changes.

## Implementation Steps

1. Add a storage helper for transactional recommendation-pool checkpoints.
2. Add service-level batching around successful topic extraction results.
3. Keep the existing final full write as the reconciliation step.
4. Add helper tests for checkpoint SQL, rollback behavior, and batch flushing.

## Verification

- `uv run python -m pytest tests/test_a_share_analysis_service_helpers.py tests/test_a_share_analysis_db_storage_helpers.py`: not run because pytest is not installed in the local virtual environment.
- `uv run python -m unittest tests.test_a_share_analysis_service_helpers tests.test_a_share_analysis_db_storage_helpers`: passed.
