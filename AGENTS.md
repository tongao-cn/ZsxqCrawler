# AGENTS.md

AI coding agent operating guidelines for this repository. Keep this file short: it is a high-signal guardrail and index, not a full project manual.

Use judgment for trivial tasks. These rules bias toward correctness, minimal diffs, and concrete verification.

## Project Snapshot

- This is a Knowledge Planet data crawler and group-level workbench for topic sync, file downloads, AI analysis, daily stock concepts, and A-share research workflows.
- Python backend code lives under `backend/`; operational commands live in `scripts/`; tests live in `tests/`.
- The Next.js frontend lives under `frontend/`; run frontend commands with `npm --prefix frontend ...`.
- Use `uv run python -m backend.main` or `uv run zsxq-api` for the backend. Root `main.py` is only a compatibility entrypoint.
- PostgreSQL schema `zsxq_core` is the structured data source of truth. Runtime code should not execute DDL by default.
- Quick start lives in `README.md`; durable architecture and workflow boundaries live in `docs/project-architecture-roadmap.md`.

## 1. Think Before Coding

Do not silently guess.

- State assumptions when they materially affect the implementation.
- If the request is ambiguous and multiple interpretations are reasonable, surface the choice.
- If a simpler or safer path exists, say so before implementing.
- If missing requirements block correct work, ask one short clarifying question.

## 2. Prefer Simple Solutions

Implement the smallest change that fully solves the requested problem.

- Do not add features, options, abstractions, or configurability that were not requested.
- Do not generalize for hypothetical future use.
- Do not add defensive fallbacks or compatibility shims for impossible internal states. Validate at system boundaries such as user input, files, databases, external APIs, and LLM output.
- If the same result can be achieved with materially less code, prefer the shorter version.

## 3. Make Surgical Changes

Keep diffs tightly scoped to the task.

- Touch only files and lines needed for the requested outcome.
- Do not refactor adjacent code unless the task requires it.
- Do not add docstrings, comments, type annotations, or cleanup to code you did not otherwise need to change.
- Match surrounding style and conventions.
- Do not remove unrelated dead code, comments, or formatting noise just because you noticed it.
- Clean up only issues directly created by your own change.
- Do not reformat whole files or projects, reorder unrelated imports, or update lockfiles unless the task requires it.

## 4. Verify The Change

Define success in a way that can be checked.

- For bug fixes, prefer reproducing the issue first, then fixing it.
- For new behavior, prefer adding or updating focused tests when the repo already has tests for that area.
- End by running the smallest meaningful verification available.
- If verification cannot run because Docker, PostgreSQL, external APIs, Cookie, or LLM keys are unavailable, record the skipped command and missing condition.

Common commands:

- Backend test: `uv run python -m unittest tests.test_xxx -v`
- Backend full test: `uv run python -m unittest discover -s tests`
- Backend syntax: `uv run python -m py_compile backend/path/to/file.py`
- Frontend build: `npm --prefix frontend run build`
- Frontend dev server for manual checks: `npm --prefix frontend run dev`
- PostgreSQL schema/access: `uv run manage-postgres-core-schema --apply` and `uv run manage-postgres-core-access --apply`
- PostgreSQL smoke: `.\scripts\run_postgres_core_smoke.ps1` or `.\scripts\run_postgres_runtime_cutover_smoke.ps1`

For storage, task runtime, architecture, or workflow-boundary changes, check `docs/project-architecture-roadmap.md` before choosing verification.

Test hygiene:

- Prefer adding focused tests to an existing same-topic test file.
- Do not move, rename, delete, or broadly reorganize tests just for cleanup.
- Keep one-off probes out of permanent tests unless they protect durable behavior.

## 5. Project Boundaries

- New structured data belongs in PostgreSQL `zsxq_core`; schema definitions belong in `backend/storage/postgres_core_schema.py`.
- Do not reintroduce SQLite runtime behavior. Keep `backend/storage/db_compat.py` as a narrow compatibility layer.
- Long-running workflows should go through the task system with clear group scope, lock behavior, status/log visibility, and cancellation semantics.
- The primary product surface is the group workbench at `/groups/[groupId]`; do not add global pages for group-scoped work unless explicitly needed.
- Keep A-share recommendation, daily stock concepts, daily topic analysis, and file AI analysis as separate product workflows even when they share helpers.
- If the user asks to use database topics for analysis, do not crawl again.

## 6. Workspace, Directories, Secrets, And Commands

- Default shell is Windows PowerShell.
- Prefer `uv run ...` for Python commands.
- Do not use `python -` for stdin scripts; use `python -c` for short snippets or a temporary `.py` file for multiline logic.
- Do not print, copy, or modify secrets from `.env` or `config.toml`; do not echo secret values back in responses.
- Put new code, scripts, tests, and docs in the existing ownership directories: `backend/`, `frontend/`, `scripts/`, `tests/`, and `docs/`.
- Do not create new top-level directories unless the task clearly needs a new durable area.
- Do not create scattered root-level JSON, logs, or exports. Use ignored paths such as `output/scratch/<run-name>/` for temporary verification and `output/exports/<workflow>/<YYYYMMDD_HHMMSS>/` for short-lived exports.
- Do not use root `tmp/` as a default scratch directory; it is not ignored in this repo.
- Do not clean `output/databases/{group_id}/downloads/` unless explicitly asked. It can contain real downloaded files.

## 7. Git And Multi-Agent Hygiene

- Work directly on `main` for future changes. Do not create or continue feature branches unless the user explicitly asks for one.
- Commit after each logically coherent and verified change.
- Stage and commit only your own changes; leave unrelated user or other-agent work untouched.
- Never overwrite, revert, delete, or move user/other-agent changes unless explicitly asked.
- Do not make destructive changes outside the requested scope.
- Before editing, staging, or committing, check `git status --short`.
- Before committing, review your own diff and ensure unrelated dirty files are not included.
- If another agent changed a file you also need, inspect the current diff and make the smallest compatible change. If ownership is unclear or changes conflict, pause and ask.

## 8. Documentation Workflow

Keep durable module details, research conclusions, and long-lived operational notes under `docs/`, not in this file.

Useful entrypoints:

- Quick start and runtime commands: `README.md`
- Architecture and boundaries: `docs/project-architecture-roadmap.md`
- PostgreSQL read contract: `docs/postgres_core_reader_usage.md`
- Active plans: `docs/*.md`
- Archived plans and reports: `docs/archive/`

Fast path is for localized changes that do not alter public APIs, durable runtime semantics, architecture boundaries, configuration semantics, research methodology, or data contracts. Read only directly relevant docs, make the smallest change, and verify.

Plan path is for higher-risk work that changes public APIs, durable runtime behavior, storage contracts, crawler behavior, AI output semantics, architecture boundaries, or needs a reusable verification/rollback trail. Reuse an existing active plan when it fits; create a short kebab-case plan only when durable tracking is needed.

Do not create docs for fast-path work unless the docs are the requested deliverable. Keep active plans finite; move completed or stale plans to `docs/archive/` when cleanup is in scope.

If docs conflict with code or with each other, pause and surface the conflict.

## Practical Default

Clarify ambiguity, choose the smallest safe path, check relevant docs, make the change, verify it, and record the outcome.

## Agent skills

### Issue tracker

Issues and PRDs are tracked as local markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-role triage vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout. See `docs/agents/domain.md`.
