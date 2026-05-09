# PostgreSQL Compatibility Deprecation Plan

## Goal

Reduce runtime dependence on SQLite-style SQL translation while keeping PostgreSQL as the only structured data backend.

## Stage 1: Stop The Bleeding

- Keep `backend/storage/db_compat.py` in place.
- Only add conflict-target mappings for tables whose primary key or unique key is already defined in `postgres_core_schema.py`.
- Add tests for mapped relation tables so legacy `INSERT OR REPLACE` cannot silently degrade to plain `INSERT`.
- Track remaining SQLite compatibility patterns with `scripts/scan_postgres_compat_debt.py`.

## Stage 2: Migrate Hot Write Paths

- Replace high-frequency file, topic, and column writes with explicit PostgreSQL SQL.
- Prefer direct `ON CONFLICT` statements in storage modules over relying on `_translate_sql()`.
- Keep behavior and data-shape tests close to each migrated module.

Stage 2 progress:

- `task_runs` now uses `ON CONFLICT(task_id)` directly.
- Account storage no longer issues SQLite `PRAGMA` calls at runtime.
- File stats no longer probes `PRAGMA table_info(files)` and assumes the managed PostgreSQL schema.
- File, topic, column, relation, video, comment, tag, and AI-analysis hot paths with existing keys use explicit PostgreSQL conflict targets.
- `collection_log`, `crawl_log`, `solutions`, and `tags` id creation paths use `RETURNING id` instead of `lastrowid`.
- Remaining scan debt is intentionally concentrated in tables without unique-key semantics: `talks`, `likes`, `latest_likes`, `like_emojis`, `user_liked_emojis`, `questions`, `answers`, and `articles`.

## Stage 3: Shrink The Compatibility Layer

- Remove SQLite SQL translation after runtime storage paths no longer need it.
- Keep only PostgreSQL connection setup, `search_path`, schema readiness errors, row-shape adaptation, and `?` parameter compatibility.
- Reject SQLite-only SQL such as `PRAGMA`, `INSERT OR REPLACE`, `INSERT OR IGNORE`, and `AUTOINCREMENT` instead of translating it silently.

Stage 3 progress:

- Runtime scan debt is cleared; `scripts/scan_postgres_compat_debt.py` reports no SQLite compatibility patterns.
- Remaining no-unique-key content tables now use ordinary `INSERT INTO`, preserving append semantics without adding conflict targets.
- `db_compat.py` no longer provides automatic upsert, pragma, DDL, or `lastrowid` translation.
- Future work for `talks`, `likes`, `latest_likes`, `like_emojis`, `user_liked_emojis`, `questions`, `answers`, and `articles` is a schema/data semantics audit, not compatibility-layer cleanup.

## Current Boundaries

- Do not invent conflict targets for tables without an existing primary key or unique key.
- Do not add new schema constraints in the stop-the-bleeding stage.
- Run `uv run python scripts/scan_postgres_compat_debt.py` after storage changes to keep the remaining debt visible.
