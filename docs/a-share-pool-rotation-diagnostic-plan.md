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

## Artifacts

- `output\a_share_research\51111112855254_pool_rotation_summary_topn_windows1_30_20260101_20260516_20260516_230812.csv`
- `output\a_share_research\51111112855254_pool_rotation_daily_topn_windows1_30_20260101_20260516_20260516_230812.csv`
- `output\a_share_research\51111112855254_pool_rotation_period_topn_windows1_30_20260101_20260516_20260516_230812.csv`
- `output\a_share_research\51111112855254_pool_rotation_diagnostic_topn_windows1_30_20260101_20260516.csv`

## Findings

- The raw best combination is `Top50 / 1日`: compound return `36.3597%`, average turnover `77.5931%`, max drawdown `-16.4682%`.
- `Top50 / 1日` is cost-sensitive: after `20bp` turnover cost, compound return drops to `19.7427%`; after `50bp`, it drops to `-1.5020%`.
- The best `20bp`-cost combinations are longer-horizon, lower-turnover variants:
  - `Top10 / 22日`: raw `27.6410%`, after `20bp` `24.3508%`, average turnover `15.6349%`, max drawdown after `20bp` `-28.0962%`.
  - `Top10 / 16日`: raw `27.3898%`, after `20bp` `23.4324%`, average turnover `18.8492%`, max drawdown after `20bp` `-27.5940%`.
  - `Top100 / 20日`: raw `25.6551%`, after `20bp` `23.3706%`, average turnover `10.9586%`, max drawdown after `20bp` `-13.6215%`.
- No tested combination reaches `100%` compound return in the available 2026 sample.
- The available evidence does not justify claiming a 100% 2026 compound-return strategy without overfitting. The best raw result is far below that threshold, and transaction-cost assumptions reduce it materially.
