# A-share Recommendation Prompt Tuning Plan

## Goal

Tighten the A-share recommendation-pool AI extraction prompt so the pool collects stocks with positive recommendation or beneficiary semantics, not every A-share company mentioned in a topic.

## Scope

- Change only the topic-level A-share recommendation-pool extraction prompt.
- Keep ranking windows, storage tables, checkpoint behavior, routes, and UI unchanged.
- Keep daily stock-concept extraction separate.

## Docs Checked

- `docs/project-architecture-roadmap.md`
- `docs/a-share-recommendation-pool-checkpoint-plan.md`
- `docs/postgres_core_reader_usage.md`

## Evidence

`五粮液` had both valid positive recommendation mentions and invalid negative/risk mentions in existing extraction evidence:

- Positive examples: investment-advice text with `重点推荐`, `首选`, `价格弹性`, `出清磨底`.
- Negative examples: `业绩调整后表现平平`, `年报出现重大调整`, `营收利润重新计算后大幅下滑`.

The old prompt extracted clearly mentioned A-share companies, so negative mentions could enter the recommendation pool.

## Execution

1. Extracted the prompt into a helper for focused tests.
2. Updated the prompt to require positive recommendation, beneficiary, catalyst, improvement, reversal, or upside semantics.
3. Explicitly excluded risk, scandal, bearish news, earnings downgrade, restatement/downward recalculation, penalty, selling pressure, negative examples, avoid/踩雷/避雷, weak performance, and sell-side flow-only contexts.
4. Bumped `TOPIC_STOCK_EXTRACTION_PROMPT_VERSION` to `a-share-topic-stock-extraction-v2`.

## Verification

- `uv run python -m unittest tests.test_a_share_analysis_service_helpers`: passed.
- `uv run python -m py_compile backend\services\a_share_analysis_service.py tests\test_a_share_analysis_service_helpers.py`: passed.
