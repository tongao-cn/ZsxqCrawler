# Analysis Report Reasoning Effort Plan

## Goal

Set analysis report style AI calls to high reasoning depth by default, without changing extraction-style AI defaults.

## Scope

- Update only the shared AI provider default used by summary/report workflows.
- Keep A-share recommendation extraction and daily stock concept extraction on the existing extraction default.

## Constraints

- Make the smallest behavior change.
- Do not read or print secrets from local `.env`.

## Docs Checked

- `README.md`
- `docs/project-architecture-roadmap.md`

## Execution Steps

1. Add focused regression coverage for summary versus extraction reasoning defaults.
2. Change the report/summary default reasoning effort.
3. Run targeted verification.

## Verification Plan

```powershell
uv run python -m unittest tests.test_ai_provider_config_helpers
uv run python -m py_compile backend\core\ai_provider_config.py
```

## Progress

- 2026-05-24: Plan created.
- 2026-05-24: Added regression coverage for summary/report default reasoning effort.
- 2026-05-24: Changed summary/report default reasoning effort to `high`.

## Changed Files

- `backend/core/ai_provider_config.py`
- `tests/test_ai_provider_config_helpers.py`
- `docs/analysis-report-reasoning-effort-plan.md`

## Verification Results

```powershell
uv run python -m unittest tests.test_ai_provider_config_helpers
# 1 passed

uv run python -m py_compile backend\core\ai_provider_config.py
# passed
```
