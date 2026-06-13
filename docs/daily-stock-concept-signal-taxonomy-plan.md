# Daily Stock Concept Signal Taxonomy Plan

## Status

Active.

This plan tracks the next optimization rounds for the stock concept tab after the first
display-layer split between industry concepts and signal tags.

## Goal

Make the stock concept workflow easier to read and more stable by separating:

- Industry concepts: stable sector or supply-chain themes such as PCB, CCL, AI算力/数据中心,
  半导体设备/先进封装, 光通信/CPO, 机器人, 储能.
- Signal tags: catalyst, style, or event attributes such as 涨价/供需, 国产替代/自主可控,
  出海/出口, 订单/扩产, 估值/分红.
- Raw terms: original model-extracted terms kept for traceability and future taxonomy tuning.

The target is not to delete fine-grained terms. The target is to keep them visible in the
right layer so the concept ranking is cleaner while signals such as 涨价 and 国产替代 remain
easy to inspect.

## Current State

- Frontend display already has a concept/signal split in the stock concept tab.
- Current frontend taxonomy is still code-local in
  `frontend/src/components/DailyTopicAnalysisPanelUtils.ts`.
- `daily_stock_concepts.concepts_json` still stores the original aggregated concept list.
- Topic-level extraction still writes only `concepts_json`; it does not yet distinguish
  industry concepts, signal tags, and raw terms.
- The latest scan found many remaining raw terms, but most are long tail. The highest-value
  cleanup should focus on frequent multi-day terms.

## Scope

In scope:

- Stock concept tab display and derived-state logic.
- Daily stock concept aggregation and normalization.
- A-share topic-level stock extraction prompt and schema, when the backend slice starts.
- Read-only diagnostics for concept coverage, signal coverage, and unmapped tail terms.

Out of scope unless explicitly requested:

- A-share recommendation pool ranking logic.
- Stock topic analysis reports.
- Return-smoke or downstream quant research outputs.
- Destructive rewrites of existing historical raw extraction rows.

## Constraints

- Preserve raw extraction evidence for traceability.
- Do not silently drop 涨价, 国产替代, 出海, 供需紧张, 扩产, or other useful signals.
- Prefer additive fields and display-layer normalization before schema-changing migrations.
- Keep each implementation slice small, verified, and committed separately.
- Leave unrelated dirty worktree changes untouched.

## Docs Checked

- `docs/project-architecture-roadmap.md`
- `docs/module-refactor-execution-plan-20260610.md`
- `docs/systematic-refactor-plan-20260611.md`
- `docs/archive/stock-topic-analysis-tab-plan.md`

## Execution Plan

### Phase 1 - Frontend Signal Usability

Goal: make the current no-schema split more useful.

Steps:

1. Add stock-table display that separates normalized industry concepts from signal tags.
2. In the detail card, show the selected concept or signal with its top related counterpart:
   - selected concept -> top signal tags under that concept.
   - selected signal -> top industry concepts under that signal.
3. Add compact counts for both views:
   - total industry concepts.
   - total signal tags.
   - unmapped raw term count.
4. Keep filtering behavior compatible with both concept and signal selection.

Verification:

- `npm run lint`
- `npx tsc --noEmit`
- Manual stock concept tab smoke on `localhost:18080` when browser runtime is available.

### Phase 2 - Taxonomy Diagnostics

Goal: stop relying on ad hoc one-off scans.

Steps:

1. Add a read-only script that reports:
   - raw concept hits.
   - raw unique terms.
   - normalized unique terms.
   - mapped versus unmapped hits.
   - top unmapped terms by topic count and active days.
2. Export the result as console output and optionally CSV.
3. Use the script before adding new alias batches.

Verification:

- Run diagnostics against the latest completed date and recent 11-day window.
- Add focused unit tests for normalization helpers if the script extracts reusable logic.

### Phase 3 - Shared Normalization Layer

Goal: move taxonomy out of frontend-only code.

Steps:

1. Create a backend normalization module, likely
   `backend/services/stock_concept_taxonomy.py`.
2. Define:
   - canonical industry concept aliases.
   - signal tag aliases.
   - noise or too-broad terms.
3. Add pure helper functions:
   - `normalize_stock_concept_terms(raw_terms)`.
   - returns `industry_concepts`, `signal_tags`, `raw_terms`, and `unmapped_terms`.
4. Keep frontend taxonomy in sync by either:
   - duplicating from a generated JSON file, or
   - exposing taxonomy through an API later.

Verification:

- Unit tests for aliases, signal tags, noise terms, and no-drop raw term behavior.
- Existing frontend lint and TypeScript checks.

### Phase 4 - Daily Concept Aggregation Cleanup

Goal: make daily stock concept API return cleaner concepts while preserving raw terms.

Steps:

1. Apply backend normalization inside `daily_stock_concept_service._aggregate_topic_stock_extractions`.
2. Keep `concepts_json` focused on canonical industry concepts for the current API.
3. Preserve raw terms either in reason text initially or in a future additive field.
4. Avoid changing topic-level raw extraction rows in this phase.

Verification:

- Focused tests for daily stock concept aggregation.
- Compare latest completed date before and after normalization:
  - top industry concepts.
  - top signal tags if exposed.
  - no loss of stock/topic evidence.

### Phase 5 - Extraction Prompt And Schema Upgrade

Goal: reduce future concept explosion at the source.

Steps:

1. Update topic-level extraction prompt to request:
   - medium-grain `industry_concepts`, maximum 3-5 per stock.
   - `signal_tags` for catalysts and attributes.
   - optional `raw_terms` for exact source wording.
2. Update JSON schema and parser.
3. Add database columns only if the no-schema approach is insufficient:
   - `signal_tags_json`
   - `raw_terms_json`
4. Keep backward compatibility for old `concepts_json` rows.

Verification:

- Parser unit tests for old and new schema shapes.
- Small no-write extraction smoke on representative topics.
- Daily concept generation smoke for one completed date.

## Open Questions

- Should `国产替代/自主可控` live only as a signal tag, or also appear as a top-level concept when
  it is the user's explicit focus?
- Should `涨价/供需` be a single signal group, or split into `涨价`, `供需紧张`, and `量价齐升`?
- Should broad terms like `半导体`, `材料`, and `设备` be hidden, shown as unmapped, or mapped only
  when no better concept exists?
- Should generated reports use the signal split, or should this remain only in the stock concept tab?

## Progress Log

### 2026-06-13 - Phase 1 Display Split Follow-Up

- Added stock-table display separation for normalized industry concepts and signal tags.
- Added selected-item related distribution:
  - selected industry concept shows top related signal tags.
  - selected signal tag shows top related industry concepts.
- Kept the implementation display-layer only; no database schema or raw extraction rows changed.
- Remaining Phase 1 work:
  - add compact unmapped raw term counts.
  - add a stronger manual browser smoke once Playwright browser binaries are available.

### 2026-06-13 - Initial Plan

- Created this plan after the display-layer concept/signal split landed.
- Current implementation keeps raw data intact and separates concept versus signal statistics in
  the frontend stock concept tab.
