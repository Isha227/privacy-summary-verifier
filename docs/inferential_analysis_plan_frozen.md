# Frozen Inferential Analysis Plan

**Frozen:** 20 August 2026, before examination of inferential significance results  
**Status:** Approved for the main study

## Experimental structure

The main study contains 30 privacy policies. Every policy was evaluated under all nine combinations of three model families (GPT, Llama and Mistral) and three prompting strategies (zero-shot, role and structured reasoning), giving 270 summaries. Policy is therefore the repeated experimental block.

## Confirmatory outcomes and models

1. Continuous summary-level outcomes (summary word count, Flesch Reading Ease and word compression ratio) will be analysed using linear mixed-effects models. Model family, prompt strategy and their interaction will be fixed effects; privacy policy will have a random intercept.
2. Gemini and MiniCheck faithfulness will be analysed separately using binomial generalized estimating equations (GEE). Each summary contributes its supported and total claim counts. Model family, prompt strategy and their interaction will be fixed effects; privacy policy will define the repeated cluster. An exchangeable working correlation will be used.
3. Human evaluation will be used for evaluator validation and agreement analysis only. It will not be used for condition-level hypothesis testing because the hybrid human sample contains unequal within-summary precision (one sampled claim for most summaries and all claims for nine summaries).

## Hypothesis-testing sequence

- The model-family main effect, prompting-strategy main effect and model-by-prompt interaction will be evaluated for each outcome.
- Follow-up pairwise comparisons will be performed only for an effect supported by the corresponding overall model test.
- Where an interaction is supported, simple effects will be preferred to marginal main-effect pairwise comparisons.
- Pairwise p-values will be adjusted using the Holm method within each outcome and comparison family.
- The significance threshold is alpha = .05, two-sided.

## Reporting

- Report estimates, 95% confidence intervals, test statistics and adjusted p-values, not p-values alone.
- Continuous-outcome coefficients are reported in the outcome's original unit.
- Faithfulness coefficients are reported as odds ratios with 95% confidence intervals; estimated marginal probabilities may be added for interpretation.
- Gemini and MiniCheck results must remain separate. Differences between their rankings or conclusions will be reported as evaluator sensitivity rather than resolved by selecting one evaluator post hoc.
- Model diagnostics, convergence warnings and departures from assumptions will be retained and disclosed. Sensitivity analyses may supplement but will not silently replace the frozen primary analysis.

## Reference levels

- Model family: GPT
- Prompt strategy: zero-shot

These reference levels affect coefficient interpretation but not the overall tests.
