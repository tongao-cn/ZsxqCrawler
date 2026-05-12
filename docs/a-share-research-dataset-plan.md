# A-share Research Dataset Plan

## Goal

Turn the existing A-share recommendation, stock-concept, and stock-topic outputs into a reusable research dataset so downstream stock research can move from "mentioned in topics" to repeatable signal review and later return testing.

## Scope

- Add a read-only export path for group-scoped A-share research signals.
- Use existing PostgreSQL `zsxq_core` tables only.
- Export one row per `group_id + signal_date + stock_name`, with topic evidence, concepts, mention count, and topic engagement metrics.
- Keep the current recommendation-pool extraction and ranking logic unchanged.
- Do not add market-price or return-calculation logic in this slice.

## Constraints

- Do not change A-share recommendation-pool output semantics.
- Do not change daily stock-concept or stock-topic analysis workflows.
- Do not add new schema objects.
- Keep the export usable by downstream projects through CSV and the reader contract.
- Keep implementation read-only against PostgreSQL.

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

## Verification Plan

- `uv run python -m unittest tests.test_a_share_research_export_service_helpers`
- `uv run python -m py_compile backend\services\a_share_research_export_service.py scripts\export_a_share_research_dataset.py`

## Progress

- Plan created.
- Added a read-only research export service that aggregates topic-level stock extraction evidence into daily stock signal rows.
- Added a CLI command to export the dataset to CSV.
- Updated the PostgreSQL reader guide with stock-research tables and export usage.
- Added helper tests for date validation, aggregation, and CSV serialization.

## Changed Files

- `docs/a-share-research-dataset-plan.md`
- `backend/services/a_share_research_export_service.py`
- `scripts/export_a_share_research_dataset.py`
- `tests/test_a_share_research_export_service_helpers.py`
- `docs/postgres_core_reader_usage.md`
- `pyproject.toml`

## Verification Results

- `uv run python -m unittest tests.test_a_share_research_export_service_helpers`: passed.
- `uv run python -m py_compile backend\services\a_share_research_export_service.py scripts\export_a_share_research_dataset.py`: passed.
- `uv run export-a-share-research-dataset --help`: passed.
