# Research Radar Product Roadmap Design

Date: 2026-06-26

## Context

ZsxqCrawler is evolving from a Knowledge Planet crawler into a group-level data workbench. The strongest product direction is an A-share research workflow that turns group content into actionable, evidence-backed research material.

The current architecture already supports this direction:

- PostgreSQL `zsxq_core` is the structured data source of truth.
- The primary product surface is `/groups/[groupId]`.
- Long-running work should go through the task runtime.
- Existing workflows already cover topic sync, file AI analysis, daily topic analysis, daily stock concepts, and A-share analysis.

This design adds a new group-scoped product surface: Research Radar.

## Product Positioning

Research Radar is the A-share opportunity discovery entrypoint inside a single group workbench. It is not a market data terminal and it does not generate trading instructions. It turns already-synced group content into a traceable pre-market research briefing.

The MVP focuses on two outcomes:

- A user can spend about five minutes reading the pre-market radar and choose three to five directions or stocks to watch.
- Every main AI conclusion can be traced back to source evidence from topics, comments, files, images, or file analysis summaries.

Research Radar should be added as a new tab under `/groups/[groupId]`, alongside the existing topics, files, daily analysis, stock concept, and A-share surfaces. It should not replace existing daily stock concept or A-share analysis workflows in the first iteration.

## User And Scope

The primary user is an A-share research user who already follows one or more Knowledge Planet groups and wants the group content converted into daily research leads.

The MVP scope is one group at a time. It uses only content already stored for that group and must not trigger a new crawl while generating radar output.

Out of scope for the MVP:

- Cross-group aggregation.
- Intraday real-time radar refresh.
- Trading recommendations, buy points, or sell points.
- Mandatory external market data, announcements, or research reports.
- Rewriting existing daily analysis or A-share analysis product semantics.
- Conclusions without source evidence.

## First Screen

The Research Radar tab should lead with today's research logic, not a raw heat ranking.

Suggested first-screen structure:

```text
Research Radar
|-- Today's Research Logic
|   |-- Logic summary
|   |-- Related directions and concepts
|   |-- Key stocks
|   `-- Evidence cards
|-- Today's Direction Board
|-- Today's Key Stocks
`-- Evidence Feed
```

The primary actions are:

- View evidence: expand source cards for a research logic item.
- Deepen stock research: open a lightweight stock research view from a key stock.

## Research Logic Definition

In this product, "research logic" means an evidence-backed change in the current group's research signals within a selected time window. It is not the same as price movement.

The MVP judgment process is:

```text
Stored topics, comments, file material, and existing extraction results
-> Extract stocks, concepts, catalysts, risks, timestamps, and source links
-> Compare against a recent baseline for heat, novelty, and co-occurrence
-> Generate candidate signals
-> Require evidence cards
-> Use AI to summarize the candidate as readable research logic
-> Output confidence and weak-signal status
```

A main-list logic item must satisfy all of these rules:

- Change: the topic window shows a new, rising, or newly combined signal compared with the recent baseline.
- Causal expression: the item explains why the direction or stock is being discussed, such as catalyst, supply-demand shift, policy, orders, expansion, localization, export, performance, or risk.
- Evidence: the item links back to at least one source topic, comment, file, image, or file analysis summary.

Display tiers:

- Strong logic: multiple evidence items, clear catalyst, and clear direction or stock chain.
- Medium logic: enough evidence, but the catalyst or stock chain is incomplete.
- Weak signal: early clue with limited evidence; shown outside the main briefing area.

AI should explain and compress evidence-backed candidates. It must not invent unsupported logic.

## Data And Evidence Model

Research Radar reads from the current group only:

- Topic body content.
- Comments.
- File metadata and file AI analysis summaries.
- Image OCR or image descriptions when already available.
- Existing stock and concept extraction results.
- Task and generation records.

The durable radar output should be stored in PostgreSQL `zsxq_core` rather than only local JSON, because it becomes a research archive and future input for post-market review and historical comparison.

Suggested conceptual records:

```text
RadarRun
RadarLogic
RadarEvidence
RadarEntity
```

Evidence cards should include:

- Source type: topic, comment, file, image, or file analysis summary.
- Source ID and source timestamp.
- Short source excerpt or summary.
- Matched stocks, concepts, catalysts, and risks.
- Explanation of why this evidence supports the logic item.
- Frontend navigation target.

Schema changes must be implemented through `backend/storage/postgres_core_schema.py` and the schema management command. Runtime code should not execute DDL by default.

## Workflow And Module Boundaries

Research Radar should be a separate workflow that reuses existing lower-level capabilities. It should not be implemented as a rename of daily stock concepts.

Suggested backend modules:

```text
backend/routes/research_radar_routes.py
backend/services/research_radar_workflow.py
backend/services/research_radar_signal.py
backend/services/research_radar_ai.py
backend/services/research_radar_store.py
```

Responsibilities:

- `research_radar_routes.py`: HTTP adapter for starting radar generation, reading latest runs, and reading run details.
- `research_radar_workflow.py`: group-scoped task entrypoint and workflow orchestration.
- `research_radar_signal.py`: candidate generation from heat, novelty, co-occurrence, catalysts, and risks.
- `research_radar_ai.py`: evidence-constrained summarization into user-readable logic.
- `research_radar_store.py`: PostgreSQL reads and writes for runs, logic items, evidence, and entities.

Frontend surface:

```text
frontend/src/components/ResearchRadarPanel.tsx
```

The workflow should use the existing task runtime. Radar generation is group-scoped, long-running work with status, logs, failure visibility, and persisted results.

Reuse boundaries:

- Reuse `topic_material` or equivalent topic/comment material readers.
- Reuse stock and concept normalization where practical.
- Reuse file AI summaries when they exist, without requiring every file to be analyzed.
- Keep daily topic analysis, daily stock concepts, and A-share analysis as separate products.

## Roadmap

### P0 - Evidence-Backed Pre-Market Radar MVP

Goal: generate a pre-market radar for one group from already-ingested content.

Included:

- New Research Radar tab.
- Manual generation task.
- Latest radar run view.
- Three to five main research logic items.
- Direction board.
- Key stock list.
- Evidence cards for each main logic item.
- Basic confidence tiering and weak-signal separation.

Success criteria:

- The user can identify three to five watch targets within about five minutes.
- Main conclusions always link to evidence.

### P1 - Stock Drilldown And Historical Comparison

Goal: make each key stock explainable beyond the current run.

Included:

- Lightweight stock research view from a radar item.
- Today's reason for appearance.
- Historical related topics, comments, files, images, and file summaries.
- Risk and catalyst continuity.
- Recent baseline comparison so the product can explain why today is different.

### P2 - Post-Market Review And Research Archive

Goal: turn daily radar output into a durable research archive.

Included:

- Post-market review generation.
- Continuation or downgrade of morning logic.
- Evidence that remained valid or became weaker.
- Date, direction, and stock archives.
- Optional later market-data validation, without making it an MVP dependency.

## Verification Strategy

For implementation planning, verification should include:

- Focused backend tests for signal candidate generation, evidence binding, store helpers, routes, and task launch.
- Schema tests if new `zsxq_core` tables are added.
- AI helper tests that enforce evidence-constrained output parsing.
- Frontend build after adding the tab and panel.
- Manual group-workbench smoke test when a local backend and frontend are available.

Suggested command families:

```powershell
uv run python -m unittest tests.test_research_radar_signal tests.test_research_radar_store tests.test_research_radar_routes_helpers -v
uv run python -m unittest tests.test_postgres_core_schema -v
npm --prefix frontend run build
```

## Design Decisions

- Use a new Research Radar tab instead of replacing existing analysis tabs.
- Keep MVP group-scoped and database-backed.
- Treat research logic as content-signal change, not price movement.
- Require evidence for main conclusions.
- Use task runtime for generation.
- Do not crawl during radar generation.
- Keep cross-group and market-data validation for later phases.
