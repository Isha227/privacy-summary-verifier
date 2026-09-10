# Results guide

This folder contains the final derived results that support the dissertation.
Each row is an analysis result, not a new model response.

## Summary quality

- summary_quality/all_540_summaries.csv — one row per generated summary.
- summary_quality/results_by_model.csv — descriptive averages for GPT, Llama
  and Mistral across all 540 summaries.

## Statistical tests

- statistics/model_effects.csv — Friedman tests comparing the three models
  using the 27 OPP-115 policies as repeated blocks.
- statistics/prompting_strategy_effects.csv — Friedman tests comparing
  zero-shot, role-based and structured prompting.
- statistics/basic_vs_safety_focused.csv — paired Wilcoxon tests for 243
  matched policy-model-strategy comparisons, with bootstrap intervals,
  rank-biserial effect sizes
  and Holm-adjusted p-values.

## Source coverage

- source_coverage/opp_coverage_by_prompt_version.csv — automated coverage for
  the 27 OPP policies.
- source_coverage/contemporary_coverage_by_prompt_version.csv — final
  researcher coverage for the three contemporary policies.
- source_coverage/evaluator_agreement.csv — Gemini–researcher agreement.

The dissertation reports the direct Covered, Partially covered and Not covered
rates. Supplementary machine-readable files may also retain weighted coverage
for auditability, but it is not used as a principal reported outcome.

## Taxonomy

- taxonomy/category_distribution.csv — source-unit counts across OPP-115.
- taxonomy/historical_vs_contemporary.csv — matched three-policy comparison
  using the same Gemini source-unit extraction, plus a separate human reference.
- taxonomy/other_items_review.csv — researcher review of units initially
  mapped to Other.
- taxonomy/validated_contemporary_additions.csv — valid Gemini additions.

Other is a review flag; it does not automatically justify a new category. A
new category would require a distinct and recurring privacy practice across
multiple policies. Only three contemporary policies were examined, so other
current policies may reveal information requiring refinement or new categories.
