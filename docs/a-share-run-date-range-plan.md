# A-Share Run Date Range Plan

## Goal

Support choosing a date range when running "生成/更新推荐池" so the task processes topics inside that range instead of only "recent N days".

## Scope

- Add optional run `start_date` / `end_date` request fields.
- Keep the existing `days` input as the fallback when no run date range is selected.
- Keep advanced reset/delete range separate from the run range.
- Update only A-share analysis backend/frontend/test/doc surfaces.

## Docs Checked

- No docs index was present under `docs/`.
- `docs/a-share-recommendation-pool-checkpoint-plan.md`
- `docs/a-share-recommendation-prompt-tuning-plan.md`

## Execution Steps

1. Backend: validate optional run date range and limit topic reads to that range.
2. Frontend: add run start/end date inputs in the generate section and send them with the run request.
3. Tests: cover date-range filtering and request payload/default behavior.
4. Verify with targeted backend unit tests and frontend lint.

## Progress

- [x] Backend date-range run support
- [x] Frontend date-range controls
- [x] Tests and verification

## Changed Files

- `backend/routes/a_share_routes.py`
- `backend/services/a_share_analysis_service.py`
- `frontend/src/components/AShareAnalysisPanel.tsx`
- `frontend/src/lib/api/types.ts`
- `tests/test_a_share_analysis_service_helpers.py`
- `tests/test_a_share_routes_helpers.py`
- `docs/a-share-run-date-range-plan.md`

## Verification Results

- `python -m unittest tests.test_a_share_analysis_service_helpers tests.test_a_share_routes_helpers`: passed.
- `python -m py_compile backend\services\a_share_analysis_service.py backend\routes\a_share_routes.py`: passed.
- `npm run lint -- --file src/components/AShareAnalysisPanel.tsx`: passed.
