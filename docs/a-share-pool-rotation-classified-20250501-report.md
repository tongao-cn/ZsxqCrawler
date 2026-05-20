# A-share Classified Pool Rotation Report 2025-05-01 to 2026-05-19

## Scope

- Group: `51111112855254`.
- Source coverage: `381` natural recommendation dates from `2025-05-01` to `2026-05-19`.
- Execution: signal day `T`, buy at the next KnowAction open, sell at the following KnowAction open.
- Cost model: one-sided turnover cost; main comparison uses `10bp = 0.10%`.
- Grid shape: `27` buckets x `30` lookback windows = `810` parameter points.
- Completed rows: every parameter point has `252` completed trading rows.

## Artifacts

- Summary: `output\a_share_research\51111112855254_pool_rotation_classified_20250501_20260519_summary.csv`
- Daily holdings: `output\a_share_research\51111112855254_pool_rotation_classified_20250501_20260519_daily.csv`
- Period returns: `output\a_share_research\51111112855254_pool_rotation_classified_20250501_20260519_period.csv`
- Contribution: `output\a_share_research\51111112855254_pool_rotation_classified_20250501_20260519_contribution.csv`
- HTML report: `output\a_share_research\51111112855254_pool_rotation_classified_20250501_20260519_report.html`

## Main Read

The refreshed sample changes the emphasis versus the shorter `2025-08-01` sample. The best raw and 10bp-adjusted points now include very short lookbacks such as `Top10 / 1日` and `rank1_10 / 1日`, but those are high-turnover and high-drawdown points. They are useful as evidence that fresh rank momentum has signal, not as an immediate default export pool.

For an actually usable pool, the better candidates split into three tiers:

- Aggressive research tier: `rank31_40 / 18日` and `rank31_40 / 24日`.
- Balanced rank-bucket tier: `rank21_40 / 25日`, with better return than TopN pools but materially higher turnover.
- Low-turnover product tier: `Top50 / 23~26日`, with better 10bp-adjusted return than `Top100 / 30日` at still-low turnover.

The current product baseline `Top100 / 30日` remains positive and low-turnover, but it is not the strongest low-turnover point in this refreshed grid. `Top50 / 26日` is the cleaner low-turnover challenger.

## Top 10bp-Adjusted Points

| Bucket | Window | 10bp return | Raw return | Avg turnover | Win rate | 10bp max DD | Read |
|---|---:|---:|---:|---:|---:|---:|---|
| `rank1_10` | 1 | 200.7614% | 274.2817% | 87.1561% | 54.7619% | -36.6719% | Very high friction |
| `Top10` | 1 | 200.7614% | 274.2817% | 87.1561% | 54.7619% | -36.6719% | Same as rank1_10 |
| `rank31_40` | 18 | 197.9526% | 246.8795% | 60.5930% | 58.3333% | -22.5093% | Strong aggressive bucket |
| `rank31_40` | 24 | 181.9925% | 223.3365% | 54.4860% | 56.3492% | -20.4541% | Aggressive but smoother |
| `Top50` | 1 | 179.6190% | 241.8626% | 80.1195% | 58.3333% | -14.1513% | High turnover |
| `rank21_40` | 25 | 170.4096% | 191.0056% | 29.2463% | 56.7460% | -15.5938% | Best balanced bucket |
| `rank21_30` | 25 | 168.9172% | 200.6608% | 44.4610% | 59.1270% | -16.7301% | Higher return, higher turnover |
| `rank56_60` | 29 | 163.9741% | 221.3640% | 78.3730% | 60.7143% | -22.0832% | High-friction tail bucket |
| `rank51_55` | 28 | 163.6664% | 219.9594% | 77.1032% | 56.7460% | -20.2047% | Concentrated tail bucket |
| `rank51_60` | 28 | 158.0741% | 200.1454% | 60.1638% | 59.9206% | -15.5508% | Tail bucket, less extreme |

## Low-Turnover Candidates

Filtering to average turnover under `10%`, `Top50` dominates the low-friction region.

| Bucket | Window | 10bp return | Raw return | Avg turnover | Win rate | 10bp max DD |
|---|---:|---:|---:|---:|---:|---:|
| `Top50` | 26 | 128.3390% | 133.6635% | 9.1844% | 58.7302% | -14.9864% |
| `Top50` | 23 | 123.4066% | 129.0810% | 9.9968% | 56.3492% | -15.1728% |
| `Top50` | 24 | 120.5988% | 126.0509% | 9.7350% | 58.7302% | -15.0074% |
| `Top50` | 27 | 120.0431% | 124.9976% | 8.8793% | 58.3333% | -15.7677% |
| `Top50` | 25 | 119.0273% | 124.2807% | 9.4492% | 58.7302% | -16.1491% |
| `Top35` | 29 | 117.7656% | 123.0299% | 9.5214% | 57.1429% | -19.2507% |
| `Top35` | 30 | 117.7548% | 122.9748% | 9.4388% | 57.5397% | -18.1386% |
| `Top100` | 30 | 109.4812% | 113.3493% | 7.2839% | 57.5397% | -13.6194% |

If the goal is one default board that is easy to hold and explain, `Top50 / 26日` is a strong challenger to the current `Top100 / 30日`: it gives about `18.86` percentage points more 10bp-adjusted compound return, with turnover rising from `7.2839%` to `9.1844%`.

## Monthly Stability

Selected best points by bucket:

| Candidate | Positive months | Weakest month | Weakest return | Best month | Best return |
|---|---:|---|---:|---|---:|
| `rank56_60 / 29日` | 10 / 13 | 2025-11 | -14.2359% | 2025-09 | 21.8277% |
| `rank51_60 / 28日` | 9 / 13 | 2025-11 | -9.0955% | 2025-12 | 30.9833% |
| `rank21_40 / 25日` | 9 / 13 | 2026-03 | -9.9382% | 2025-08 | 24.8966% |
| `rank21_30 / 25日` | 9 / 13 | 2026-03 | -11.0380% | 2025-08 | 27.2850% |
| `Top100 / 1日` | 12 / 13 | 2026-03 | -9.4441% | 2026-04 | 17.2100% |
| `Top50 / 1日` | 12 / 13 | 2026-03 | -6.6574% | 2025-08 | 22.5522% |

The ranking buckets earn more, but their weak months are sharper. `Top50` and `Top100` prefix pools are more stable month-to-month, especially when paired with longer windows.

## Contribution Notes

- `rank21_40 / 25日` contributors are not single-stock dominated. The top names include `宏和科技`, `香农芯创`, `长光华芯`, `烽火通信`, and `海博思创`.
- `rank56_60 / 29日` is more event-driven and concentrated. Top contributors include `光库科技`, `斯瑞新材`, `上纬新材`, `优刻得`, and `天际股份`; several only have very short holding histories.
- `Top50 / 1日` is broader but still leans on AI/optical/electronics names such as `中际旭创`, `天际股份`, `东山精密`, `宏和科技`, and `天孚通信`.

## Recommendation

Keep `30日 Top100` as a conservative baseline only if the priority is breadth and low churn. If the next UI/export iteration can change the default, the data now supports testing `Top50 / 26日` as the main board. It keeps turnover below `10%`, improves 10bp-adjusted compound return, and remains easy to explain.

For research rather than production, prioritize:

- `rank21_40 / 25日` as the balanced rank-bucket candidate.
- `rank31_40 / 18~24日` as the aggressive high-return candidate.
- `rank56_60 / 29日` only as a high-friction, event-driven satellite.

Do not promote `Top10 / 1日` or `rank1_10 / 1日` directly despite their top headline return. Their `87%` average turnover and `-36.67%` 10bp max drawdown make them poor default-board candidates.
