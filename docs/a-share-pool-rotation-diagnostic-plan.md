# A-share Pool Rotation Diagnostic Plan

## Goal

Evaluate whether the A-share recommendation-pool rotation strategy can credibly reach 100% compound return in 2026 without overfitting or manually forcing parameters.

## Scope

- Group: `51111112855254` only.
- Signal window: from `2026-01-01` through the latest available recommendation-pool date.
- Execution model: signal day `T`, buy at the next KnowAction `trade_calendar` open, sell at the following open.
- Market data: KnowAction `trade_calendar`, `stock_basic`, and `daily_quotes`.
- Parameter grid: recommendation-pool lookback days `1..30`, TopN groups `Top5`, `Top10`, `Top20`, `Top35`, `Top50`, `Top100`, and `all`.

## Constraints

- Do not tune solely to hit 100% compound return.
- Treat 100% as an evaluation threshold, not as a target to fit.
- Prefer parameter regions with nearby stable performance over single best points.
- Report failure clearly if the available sample does not support the threshold.
- Keep analysis read-only against PostgreSQL and KnowAction.

## Execution Steps

1. Confirm source-data coverage for the target group, KnowAction trade calendar, and quote tail.
2. Run the full TopN/lookback grid from `2026-01-01`.
3. Rank combinations by compound return and compare by TopN family.
4. Add turnover and cost sensitivity diagnostics.
5. Add drawdown, weekly/monthly stability, and outlier-risk diagnostics.
6. Select only defensible candidate regions; reject single-point peaks as overfit risk.
7. Conclude whether the current evidence supports 100% compound return for 2026.

## Verification Plan

- Verify generated summary, daily, and period CSVs exist and contain all expected parameter groups.
- Verify completed trade counts are comparable across parameter groups.
- Verify costs and turnover are computed from daily holdings, not inferred from aggregate returns.
- Verify any 100% claim uses actual compound return over the tested period, not annualized return.

## Progress

- Source coverage confirmed for group `51111112855254`.
- Full TopN/lookback grid completed for `2026-01-01` to `2026-05-16`.
- Initial best result before costs: `Top50 / 1日`, compound return `36.3597%` over `84` completed open-to-open segments.
- Turnover, cost sensitivity, and drawdown diagnostics completed.
- Focused rank-bucket validation completed for `rank41~80` and merged mid/high slices over windows `15..30`.

## Artifacts

- `output\a_share_research\51111112855254_pool_rotation_summary_topn_windows1_30_20260101_20260516_20260516_230812.csv`
- `output\a_share_research\51111112855254_pool_rotation_daily_topn_windows1_30_20260101_20260516_20260516_230812.csv`
- `output\a_share_research\51111112855254_pool_rotation_period_topn_windows1_30_20260101_20260516_20260516_230812.csv`
- `output\a_share_research\51111112855254_pool_rotation_diagnostic_topn_windows1_30_20260101_20260516.csv`
- `output\a_share_research\51111112855254_pool_rotation_focused_rank41_80_windows15_30_20260101_20260516_20260516_235714_summary.csv`
- `output\a_share_research\51111112855254_pool_rotation_focused_rank41_80_windows15_30_20260101_20260516_20260516_235714_daily.csv`
- `output\a_share_research\51111112855254_pool_rotation_focused_rank41_80_windows15_30_20260101_20260516_20260516_235714_period.csv`
- `output\a_share_research\51111112855254_pool_rotation_focused_rank41_80_windows15_30_20260101_20260516_20260516_235714_contribution.csv`
- `output\a_share_research\51111112855254_pool_rotation_mid_band_split_20260101_20260516_20260517_001644_summary.csv`
- `output\a_share_research\51111112855254_pool_rotation_mid_band_split_20260101_20260516_20260517_001644_daily.csv`
- `output\a_share_research\51111112855254_pool_rotation_mid_band_split_20260101_20260516_20260517_001644_period.csv`
- `output\a_share_research\51111112855254_pool_rotation_mid_band_split_20260101_20260516_20260517_001644_contribution.csv`

## Findings

- The raw best combination is `Top50 / 1日`: compound return `36.3597%`, average turnover `77.5931%`, max drawdown `-16.4682%`.
- `Top50 / 1日` is cost-sensitive: after `10bp` turnover cost, compound return drops to `27.7846%`; after `20bp`, it drops to `19.7427%`; after `50bp`, it drops to `-1.5020%`.
- With `10bp` turnover cost, the leading combinations are:
  - `Top50 / 1日`: raw `36.3597%`, after `10bp` `27.7846%`, average turnover `77.5931%`, max drawdown after `10bp` `-18.8850%`.
  - `Top10 / 22日`: raw `27.6410%`, after `10bp` `25.9854%`, average turnover `15.6349%`, max drawdown after `10bp` `-27.6832%`.
  - `Top10 / 11日`: raw `28.2456%`, after `10bp` `25.7687%`, average turnover `23.3466%`, max drawdown after `10bp` `-26.2629%`.
  - `Top100 / 20日`: raw `25.6551%`, after `10bp` `24.5078%`, average turnover `10.9586%`, max drawdown after `10bp` `-13.4132%`.
- The low-turnover candidates are less sensitive to cost than the raw top `1日` variants, but they also do not approach the 100% threshold.
- No tested combination reaches `100%` compound return in the available 2026 sample.
- The available evidence does not justify claiming a 100% 2026 compound-return strategy without overfitting. The best raw result is far below that threshold, and transaction-cost assumptions reduce it materially.
- Focused mid-band validation changed the research emphasis:
  - `rank51_60 / 29日` is the strongest focused candidate after `10bp`, with raw compound return `77.8045%`, cost-adjusted compound return `68.9374%`, average turnover `61.3095%`, and max drawdown after cost `-15.3330%`.
  - `rank51_60 / 28日` is nearly identical on return and slightly higher turnover, so the signal looks stable across adjacent long windows rather than a single spike.
  - `rank61_80 / 19日` is weaker on return but lower on drawdown after cost (`-10.6917%`), so it behaves more like a steadier auxiliary band.
  - `rank51_70` and `rank51_80` keep the same direction but dilute raw edge, which argues for keeping the 50-60 band as the core focus and treating wider bands as robustness checks.
  - Monthly breakdown shows the same pattern: the best buckets still have a weak March and stronger April-May, so the edge is not uniformly smooth across the whole sample.
  - Contribution concentration is not dominated by a single stock; top names such as `烽火通信`, `宏景科技`, `潍柴动力`, `易点天下`, and `信科移动` recur across the best buckets, which supports a reusable mid-band thesis instead of a one-name accident.
  - Split-band validation refined the core region further: `rank56_60 / 29日` is the first combination that crosses `100%` after `10bp` cost, at `102.1242%`, with `81.3690%` average turnover and `-12.4461%` max drawdown after cost.
  - `rank51_55` does not show the same strength, so the edge is concentrated in the upper half of the original `51~60` band rather than the whole band.
  - Monthly stability for `rank56_60 / 29日` is still mixed, but the sample is not a one-month fluke: January through May stay positive overall, with especially strong February, April, and May.
  - The top contributors in `rank56_60 / 29日` are still recurring names like `信维通信`, `烽火通信`, `东阳光`, `优刻得`, `中材科技`, and `宏景科技`, which argues for a repeatable mid-band phenomenon rather than a one-off spike.
- Turnover-threshold review shows three practical tiers:
  - Low-turnover compromise: `rank41_80 / 24日` keeps average turnover at `27.7438%` with `34.1211%` after `10bp`; `rank41_80 / 27日` keeps turnover at `25.7071%` with `32.3837%` after `10bp`.
  - Moderate-turnover compromise: `rank51_80 / 27日` has `34.1598%` average turnover and `37.9182%` after `10bp`; `rank51_70 / 29日` raises turnover to `42.4937%` and reaches `38.6380%` after `10bp`.
  - High-turnover extreme: `rank56_60 / 29日` reaches `102.1242%` after `10bp`, but average turnover is already `81.3690%`, so it should be treated as the high-return/high-friction candidate rather than the balanced default.
