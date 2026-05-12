# A-share Research Dataset Plan

## Goal

Turn the existing A-share recommendation, stock-concept, and stock-topic outputs into a reusable research dataset so downstream stock research can move from "mentioned in topics" to repeatable signal review and later return testing.

## Scope

- Add a read-only export path for group-scoped A-share research signals.
- Use existing PostgreSQL `zsxq_core` tables only.
- Export one row per `group_id + signal_date + stock_name`, with topic evidence, concepts, mention count, and topic engagement metrics.
- Add a first return-smoke layer using KnowActionSystem `daily_quotes` as the only market data source.
- Keep the current recommendation-pool extraction and ranking logic unchanged.

## Constraints

- Do not change A-share recommendation-pool output semantics.
- Do not change daily stock-concept or stock-topic analysis workflows.
- Do not add new schema objects.
- Keep the export usable by downstream projects through CSV and the reader contract.
- Keep implementation read-only against PostgreSQL.
- Use KnowActionSystem market data for return checks; do not introduce a second market data source.

## Docs Checked

- `AGENTS.md`
- `docs/project-architecture-roadmap.md`
- `docs/stock-topic-analysis-tab-plan.md`
- `docs/postgres_core_reader_usage.md`

## Execution Steps

1. Add a small backend service that queries topic-level A-share extractions, daily mention counts, and topic metrics.
2. Aggregate rows into daily stock signal records.
3. Add a CLI script to write CSV output for a selected group and optional date range.
4. Add focused helper tests for aggregation, date validation, and CSV shape.
5. Update the reader documentation with the stock-research table contract and export command.
6. Add a KnowActionSystem-backed return smoke that evaluates T+1 open entry to T+N tradable close exit.
7. Add a CLI script to write return-smoke CSV plus a compact summary.

## Verification Plan

- `uv run python -m unittest tests.test_a_share_research_export_service_helpers`
- `uv run python -m unittest tests.test_a_share_research_return_smoke_service_helpers`
- `uv run python -m py_compile backend\services\a_share_research_export_service.py backend\services\a_share_research_return_smoke_service.py scripts\export_a_share_research_dataset.py scripts\run_a_share_research_return_smoke.py`

## Progress

- Plan created.
- Added a read-only research export service that aggregates topic-level stock extraction evidence into daily stock signal rows.
- Added a CLI command to export the dataset to CSV.
- Updated the PostgreSQL reader guide with stock-research tables and export usage.
- Added helper tests for date validation, aggregation, and CSV serialization.
- Added a KnowActionSystem-backed return-smoke service and CLI using `daily_quotes`.
- Validated a real group smoke for `51111112855254`, `2026-05-01` to `2026-05-12`, `hold_days=5`; the run wrote `output\a_share_research\51111112855254_return_smoke_20260501_20260512.csv`.
- The real smoke completed technically, but all completed rows were marked `completed_forced_end_of_sample` because the signal window is close to the current quote tail. Treat it as plumbing validation, not a formal performance conclusion.

## Changed Files

- `docs/a-share-research-dataset-plan.md`
- `backend/services/a_share_research_export_service.py`
- `backend/services/a_share_research_return_smoke_service.py`
- `scripts/export_a_share_research_dataset.py`
- `scripts/run_a_share_research_return_smoke.py`
- `tests/test_a_share_research_export_service_helpers.py`
- `tests/test_a_share_research_return_smoke_service_helpers.py`
- `docs/postgres_core_reader_usage.md`
- `pyproject.toml`

## Verification Results

- `uv run python -m unittest tests.test_a_share_research_export_service_helpers`: passed.
- `uv run python -m py_compile backend\services\a_share_research_export_service.py scripts\export_a_share_research_dataset.py`: passed.
- `uv run export-a-share-research-dataset --help`: passed.
- `uv run python -m unittest tests.test_a_share_research_return_smoke_service_helpers`: passed.
- `uv run python -m unittest tests.test_a_share_research_export_service_helpers tests.test_a_share_research_return_smoke_service_helpers`: passed.
- `uv run python -m py_compile backend\services\a_share_research_export_service.py backend\services\a_share_research_return_smoke_service.py scripts\export_a_share_research_dataset.py scripts\run_a_share_research_return_smoke.py`: passed.
- `uv run run-a-share-research-return-smoke --help`: passed.
- `uv run run-a-share-research-return-smoke --group-id 51111112855254 --start-date 2026-05-01 --end-date 2026-05-12 --hold-days 5 --output output\a_share_research\51111112855254_return_smoke_20260501_20260512.csv`: passed; rows `2277`, completed `1867`, skipped `410`, mean return `0.023207`, median return `0.012667`, win rate `0.624531`, with all completed rows flagged as forced end-of-sample.
