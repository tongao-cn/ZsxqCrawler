# A-share Pool Rotation Diagnostic Plan

## Goal

Re-run the A-share recommendation-pool rotation backtest after the recommendation-pool history was rebuilt through `2025-08-01` to `2026-05-19`, and replace the older `2026-01-01` sample conclusions.

## Scope

- Group: `51111112855254` only.
- Signal window: `2025-08-01` through `2026-05-19`.
- Execution model: signal day `T`, buy at the next KnowAction `trade_calendar` open, sell at the following open.
- Market data: KnowAction `trade_calendar`, `stock_basic`, and `daily_quotes`.
- Cost model: one-sided effective turnover cost, main case `10bp = 0.10%`.
- Parameter grid:
  - TopN prefix pools: `Top5`, `Top10`, `Top20`, `Top35`, `Top50`, `Top100`, and `all`.
  - Rank buckets: `rank1_10` through `rank91_100`, width-20 buckets, and focused buckets including `rank21_40`, `rank51_60`, `rank56_60`, and `rank51_80`.
  - Lookback windows: `1..30`.

## Constraints

- Treat all older `2026-01-01` to `2026-05-16` pool-rotation results as superseded.
- Do not tune solely to hit `100%` compound return.
- Prefer parameter regions with nearby stable performance over single best points.
- Report turnover and cost sensitivity alongside return.
- Keep analysis read-only against PostgreSQL and KnowAction.

## Execution Steps

1. Confirm rebuilt recommendation-pool source coverage.
2. Run the full TopN, rank-bucket, and focused split grid.
3. Rank combinations by `10bp` cost-adjusted compound return.
4. Compare high-return and lower-turnover candidates.
5. Check monthly stability and stock contribution concentration.
6. Replace older conclusions with the rebuilt-sample conclusions.

## Verification Plan

- Verify generated summary, daily, period, and contribution CSVs exist.
- Verify completed trade counts are comparable across parameter groups.
- Verify trade dates use KnowAction `trade_calendar`, not inferred quote dates.
- Verify costs and turnover are computed from daily holdings.
- Verify claims use actual compound return over the tested period, not annualized return.

## Progress

- Source coverage confirmed: `291` natural recommendation dates from `2025-08-01` to `2026-05-19`.
- Source records: `64,690` stock-day records and `88,135` mention counts.
- Market data loaded: `198` KnowAction trade dates and `693,076` quote rows.
- Rebuilt grid completed: `840` summary rows, `159,600` daily rows, `42,840` period rows, and `600` contribution rows.
- Completed daily rows: `157,920`; skipped rows: `1,680` due to no completed holding.
- Completed exit-date range: `2025-08-05` to `2026-05-19`.
- Older `pool_rotation` CSV outputs for group `51111112855254` were removed from `output\a_share_research`; only the rebuilt run remains there.

## Artifacts

- `output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_summary.csv`
- `output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_daily.csv`
- `output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_period.csv`
- `output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_contribution.csv`
- `output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_report.html`

## Visualization

- Generated a static HTML report with rank/day heatmaps, TopN heatmap, return-turnover scatter, candidate monthly lines, and quick-ranking tables.
- The main heatmaps and scatter use `summary.csv` `compound_after_10bps`.
- The monthly chart uses `period.csv` raw monthly `compound_return`; it is a stability view and is not cost-adjusted because `period.csv` does not carry turnover/cost columns.
- Regenerate with:

```powershell
python scripts\generate_a_share_pool_rotation_report.py --summary output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_summary.csv --period output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_period.csv --output output\a_share_research\51111112855254_pool_rotation_rebuilt_20250801_20260519_20260519_200011_report.html --title "51111112855254 A股推荐池轮动回测图表报告"
```

## Extended Window Check

- Because `rank21_40 / 30日` sat on the original `1..30` upper bound, a focused `1..60` rerun was generated for `rank21_40`, `rank21_30`, `rank56_60`, and `Top50`.
- Extended artifacts:
  - `output\a_share_research\51111112855254_pool_rotation_extended_20250801_20260519_20260519_1_60_focused_summary.csv`
  - `output\a_share_research\51111112855254_pool_rotation_extended_20250801_20260519_20260519_1_60_focused_daily.csv`
  - `output\a_share_research\51111112855254_pool_rotation_extended_20250801_20260519_20260519_1_60_focused_period.csv`
  - `output\a_share_research\51111112855254_pool_rotation_extended_20250801_20260519_20260519_1_60_focused_contribution.csv`
  - `output\a_share_research\51111112855254_pool_rotation_extended_20250801_20260519_20260519_1_60_focused_report.html`
- Extended run shape: `240` summary rows, `45,600` daily rows, `12,240` period rows, and `2,400` contribution rows; every parameter point has `188` completed trading rows.
- In the focused extended run, `rank21_40` still peaks at `30日`: after `10bp` `140.9121%`, raw `151.8566%`, average turnover `23.7752%`, max drawdown after `10bp` `-11.0514%`.
- `rank21_40 / 31日` remains close but lower: after `10bp` `133.9418%`, raw `144.1338%`, average turnover `22.7926%`, max drawdown after `10bp` `-12.7579%`.
- The high-return `rank56_60` bucket remains strongest around the original region: `rank56_60 / 29日` is the focused extended best point, after `10bp` `221.7891%`, raw `271.7250%`, average turnover `77.2163%`, max drawdown after `10bp` `-23.2725%`.
- The longer `rank56_60 / 39日` point is still useful as a lower-drawdown neighbor: after `10bp` `209.3565%`, raw `254.6918%`, average turnover `73.2181%`, max drawdown after `10bp` `-14.3947%`.
- `Top50` does not improve in the longer-window region: the best `31..60日` point is `Top50 / 35日`, after `10bp` `91.7457%`, average turnover `6.9468%`.
- Overlap note: the focused script reruns from the current DB state and explicitly slices by source rank. Old `1..30` rebuilt CSVs remain the prior baseline, but the new extended CSV is the better artifact for studying `31..60日` behavior and carries `source_rank` in holdings for future audits.
- Regenerate the focused extended grid with `python scripts\run_a_share_pool_rotation_grid.py --group-id 51111112855254 --start-date 2025-08-01 --end-date 2026-05-19 --windows 1-60 --buckets "rank21_40,rank21_30,rank56_60,top50" --output-prefix output\a_share_research\51111112855254_pool_rotation_extended_20250801_20260519_20260519_1_60_focused`.

## Findings

- The old `50~80` conclusion is no longer the main conclusion after extending history back to `2025-08-01`.
- The strongest high-return point is still a narrow mid-band:
  - `rank56_60 / 29日`: raw compound `226.2754%`, after `10bp` `182.0468%`, average turnover `77.9255%`, win rate `65.9574%`, max drawdown after `10bp` `-23.2725%`.
  - This remains a high-return/high-friction candidate, not a balanced default.
- The rebuilt sample's more useful balanced region moved forward to `rank21~40`:
  - `rank21_40 / 30日`: after `10bp` `139.9735%`, average turnover `24.3673%`, win rate `61.7021%`, max drawdown after `10bp` `-11.0514%`.
  - `rank21_40 / 24日`: after `10bp` `139.7651%`, average turnover `28.7990%`, win rate `62.7660%`, max drawdown after `10bp` `-15.6859%`.
  - `rank21_40 / 23日`: after `10bp` `139.6533%`, average turnover `29.7102%`, win rate `62.2340%`, max drawdown after `10bp` `-15.6894%`.
- If allowing moderate turnover:
  - `rank21_30 / 22日`: after `10bp` `168.4080%`, average turnover `49.0189%`, win rate `63.2979%`, max drawdown after `10bp` `-15.9096%`.
  - `rank21_30 / 27日`: after `10bp` `142.1337%`, average turnover `43.2210%`, max drawdown after `10bp` `-13.9098%`.
- TopN prefix pools are usable but weaker than rank-bucket pools:
  - Best prefix high-turnover point is `Top35 / 1日`, after `10bp` `133.3228%`, average turnover `80.9387%`.
  - Best prefix low-turnover points cluster around `Top50 / 19~30日`, after `10bp` roughly `90%~101%`, average turnover about `8%~12%`.
- Monthly behavior:
  - `rank21_40 / 30日` is the best balanced candidate: positive in most months, weak in `2025-11` and `2026-03`, with better drawdown than the narrower high-return bands.
  - `rank21_30 / 22日` earns more but has a sharper weak `2026-03`.
  - `rank56_60 / 29日` has very strong return but also a weak `2025-11` and higher turnover.
- Contribution checks do not show a single-stock-only result:
  - `rank21_40 / 30日` leading contributors include `香农芯创`, `新易盛`, `烽火通信`, `海博思创`, `上海港湾`, `长飞光纤`, `信维通信`, and `信科移动`.
  - `rank21_30 / 22日` leading contributors include `长飞光纤`, `新易盛`, `斯瑞新材`, `长光华芯`, `烽火通信`, and `阿特斯`.
  - `rank56_60 / 29日` leading contributors include `光库科技`, `五洲新春`, `通宇通讯`, `东山精密`, `优刻得`, and `华峰测控`.

## Current Candidate Tiers

- Balanced default candidate: `rank21_40 / 30日`.
- Higher-return moderate-turnover candidate: `rank21_30 / 22日`.
- High-return/high-friction candidate: `rank56_60 / 29日`.
- Conservative TopN fallback: `Top50 / 26日`.

## Product Strategy Update

- Frontend recommendation-pool defaults now reflect the research direction:
  - The main operating view is now a single `30日 Top100` pool.
  - Each stock row shows rank movement against the previous data day's same-window Top100: new entry, moved up, moved down, or unchanged.
  - `3日` is removed from the default main view to avoid steering users toward high-turnover short-cycle behavior.
- Tongdaxin export defaults to the single `30日 Top100` pool.
- Tongdaxin export now creates missing custom blocks in `blocknew.cfg` automatically before writing `.blk` files, so users no longer need to pre-create the board names manually.
- The frontend still keeps date filtering and chart TopN controls separate from the recommendation-pool strategy; chart TopN controls line visibility, not the exported pool size.

## Implementation Update 2026-05-20

- Scope: align the frontend display and Tongdaxin export behavior with the single `30日 Top100` operating view.
- Changed files:
  - `frontend/src/components/AShareAnalysisPanel.tsx`: render one `30日 Top100` recommendation table and show rank-movement badges.
  - `frontend/src/lib/api/types.ts`: expose rank movement fields on recommendation rows.
  - `backend/services/a_share_analysis_service.py`: default to `30日 Top100` and attach rank movement by comparing with the previous data day.
  - `backend/services/tdx_a_share_export_service.py`: export only the 30-day pool by default while keeping automatic Tongdaxin block creation.
  - `tests/test_a_share_analysis_service_helpers.py` and `tests/test_tdx_a_share_export_service_helpers.py`: add regression coverage for defaults, movement calculation, and TDX export windows.
- Verification:
  - `python -m unittest tests.test_tdx_a_share_export_service_helpers`
  - `python -m unittest tests.test_a_share_analysis_service_helpers`
  - `npm run lint`
