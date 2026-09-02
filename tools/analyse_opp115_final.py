from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "data" / "opp115" / "experiment"
OUT = ROOT / "outputs" / "019ff723-17a0-7bf2-84ad-aacfae5c5b43" / "final_analysis_v3"
OUT.mkdir(parents=True, exist_ok=True)

KEY = EXP / "anonymised" / "BLINDING_KEY_RESTRICTED.csv"
READABILITY = EXP / "evaluations" / "readability_compression.csv"
GEMINI = EXP / "evaluations" / "faithfulness" / "gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"
MINICHECK = EXP / "evaluations" / "faithfulness" / "minicheck_opp115_claim_scores_FINAL.csv"
COVERAGE = EXP / "coverage_v3" / "evaluations" / "gemini_coverage_scores.csv"

MODEL_ORDER = ["gpt", "llama", "mistral"]
STRATEGY_ORDER = ["Zero-shot", "Role-based", "Structured"]
SET_ORDER = ["Basic", "Safety-focused"]


def prompt_labels(raw: str) -> tuple[str, str]:
    prompt_set = "Safety-focused" if raw.startswith("safety_focused_") else "Basic"
    if raw.endswith("_direct"):
        strategy = "Zero-shot"
    elif raw.endswith("_role_guided"):
        strategy = "Role-based"
    elif raw.endswith("_structured"):
        strategy = "Structured"
    else:
        raise ValueError(f"Unexpected prompt strategy: {raw}")
    return prompt_set, strategy


def holm_adjust(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=float)
    running = 0.0
    m = len(p)
    for rank, original_index in enumerate(order):
        value = min(1.0, (m - rank) * p[original_index])
        running = max(running, value)
        adjusted[original_index] = running
    return adjusted.tolist()


def average_ranks(values: np.ndarray) -> np.ndarray:
    """Return one-based average ranks with deterministic tie handling."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        average = ((start + 1) + end) / 2.0
        ranks[order[start:end]] = average
        start = end
    return ranks


def wilcoxon_signed_rank(diff: np.ndarray) -> tuple[float, float]:
    """Two-sided Wilcoxon signed-rank test using the tie-corrected normal approximation."""
    values = np.asarray(diff, dtype=float)
    values = values[np.isfinite(values) & (values != 0)]
    if values.size == 0:
        return 0.0, 1.0
    ranks = average_ranks(np.abs(values))
    positive = float(ranks[values > 0].sum())
    negative = float(ranks[values < 0].sum())
    statistic = min(positive, negative)
    n = values.size
    mean = n * (n + 1) / 4.0
    _, tie_counts = np.unique(np.abs(values), return_counts=True)
    tie_adjustment = float(np.sum(tie_counts**3 - tie_counts)) / 48.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0 - tie_adjustment
    if variance <= 0:
        return statistic, 1.0
    z = max(0.0, abs(positive - mean) - 0.5) / math.sqrt(variance)
    p_value = math.erfc(z / math.sqrt(2.0))
    return statistic, float(min(1.0, max(0.0, p_value)))


def friedman_three_level(matrix: np.ndarray) -> tuple[float, float]:
    """Friedman test for three repeated levels; df=2 has survival exp(-Q/2)."""
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != 3:
        raise ValueError("This analysis expects exactly three repeated factor levels")
    n, k = matrix.shape
    ranked = np.vstack([average_ranks(row) for row in matrix])
    column_sums = ranked.sum(axis=0)
    statistic = 12.0 * np.sum(column_sums**2) / (n * k * (k + 1)) - 3.0 * n * (k + 1)
    tie_sum = 0.0
    for row in matrix:
        _, counts = np.unique(row, return_counts=True)
        tie_sum += float(np.sum(counts**3 - counts))
    correction = 1.0 - tie_sum / (n * (k**3 - k))
    if correction > 0:
        statistic /= correction
    else:
        statistic = 0.0
    p_value = math.exp(-max(0.0, statistic) / 2.0)  # chi-square survival, df=2
    return float(statistic), float(p_value)


def rank_biserial(diff: np.ndarray) -> float:
    diff = np.asarray(diff, dtype=float)
    diff = diff[np.isfinite(diff) & (diff != 0)]
    if diff.size == 0:
        return 0.0
    ranks = average_ranks(np.abs(diff))
    total = ranks.sum()
    return float((ranks[diff > 0].sum() - ranks[diff < 0].sum()) / total)


def bootstrap_mean_ci(values: np.ndarray, seed: int = 20260830, reps: int = 10000) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(reps, values.size), replace=True).mean(axis=1)
    lo, hi = np.quantile(samples, [0.025, 0.975])
    return float(lo), float(hi)


def wilcoxon_row(metric: str, left: str, right: str, diff: np.ndarray, family: str) -> dict:
    diff = np.asarray(diff, dtype=float)
    diff = diff[np.isfinite(diff)]
    nonzero = diff[diff != 0]
    if nonzero.size:
        statistic, p_value = wilcoxon_signed_rank(diff)
    else:
        statistic = 0.0
        p_value = 1.0
    ci_low, ci_high = bootstrap_mean_ci(diff)
    sd = float(np.std(diff, ddof=1)) if diff.size > 1 else float("nan")
    return {
        "family": family,
        "metric": metric,
        "comparison": f"{right} minus {left}",
        "n_policies": int(diff.size),
        "mean_difference": float(np.mean(diff)),
        "median_difference": float(np.median(diff)),
        "bootstrap_95ci_low": ci_low,
        "bootstrap_95ci_high": ci_high,
        "wilcoxon_statistic": statistic,
        "p_value": p_value,
        "rank_biserial": rank_biserial(diff),
        "cohen_dz": float(np.mean(diff) / sd) if sd and np.isfinite(sd) else 0.0,
    }


key = pd.read_csv(KEY)
readability = pd.read_csv(READABILITY)
gemini = pd.read_csv(GEMINI)
minicheck = pd.read_csv(MINICHECK)
coverage = pd.read_csv(COVERAGE)

for frame, name in [(gemini, "Gemini"), (minicheck, "MiniCheck"), (coverage, "coverage")]:
    if "status" in frame and not frame["status"].eq("success").all():
        raise RuntimeError(f"{name} contains non-success rows")

key[["prompt_set", "prompting_strategy"]] = key["prompt_strategy"].apply(lambda x: pd.Series(prompt_labels(x)))

gemini["is_supported"] = gemini["label"].eq("Supported").astype(int)
gemini["is_partial"] = gemini["label"].eq("Partially supported").astype(int)
gemini["is_contradicted"] = gemini["label"].eq("Contradicted").astype(int)
gemini["is_unsupported"] = gemini["label"].eq("Unsupported").astype(int)
gagg = gemini.groupby("blind_id", as_index=False).agg(
    claim_count=("claim_id", "nunique"),
    supported_claims=("is_supported", "sum"),
    partially_supported_claims=("is_partial", "sum"),
    contradicted_claims=("is_contradicted", "sum"),
    unsupported_claims=("is_unsupported", "sum"),
)
gagg["gemini_source_alignment_rate"] = gagg["supported_claims"] / gagg["claim_count"]
gagg["gemini_weighted_alignment_rate"] = (gagg["supported_claims"] + 0.5 * gagg["partially_supported_claims"]) / gagg["claim_count"]
gagg["distortion_rate"] = gagg["partially_supported_claims"] / gagg["claim_count"]
gagg["hallucination_rate"] = (gagg["unsupported_claims"] + gagg["contradicted_claims"]) / gagg["claim_count"]
gagg["source_alignment_failure_rate"] = 1 - gagg["gemini_source_alignment_rate"]

magg = minicheck.groupby("blind_id", as_index=False).agg(
    minicheck_claim_count=("claim_id", "nunique"),
    minicheck_supported_rate=("predicted_supported", "mean"),
    minicheck_mean_probability=("support_probability", "mean"),
)

coverage["is_covered"] = coverage["coverage_label"].eq("Covered").astype(int)
coverage["is_partial_coverage"] = coverage["coverage_label"].eq("Partially covered").astype(int)
coverage["is_not_covered"] = coverage["coverage_label"].eq("Not covered").astype(int)
cagg = coverage.groupby("blind_id", as_index=False).agg(
    source_unit_count=("unit_id", "nunique"),
    covered_units=("is_covered", "sum"),
    partially_covered_units=("is_partial_coverage", "sum"),
    omitted_units=("is_not_covered", "sum"),
)
cagg["strict_coverage_rate"] = cagg["covered_units"] / cagg["source_unit_count"]
cagg["weighted_coverage_rate"] = (cagg["covered_units"] + 0.5 * cagg["partially_covered_units"]) / cagg["source_unit_count"]
cagg["omission_rate"] = cagg["omitted_units"] / cagg["source_unit_count"]

summary = key.merge(readability, on=["run_id", "policy_id", "model_family", "prompt_strategy", "replicate"], how="left", validate="one_to_one")
summary = summary.merge(gagg, on="blind_id", how="left", validate="one_to_one")
summary = summary.merge(magg, on="blind_id", how="left", validate="one_to_one")
summary = summary.merge(cagg, on="blind_id", how="left", validate="one_to_one")

if len(summary) != 486 or summary["blind_id"].nunique() != 486:
    raise RuntimeError("Summary-level merge did not produce 486 unique summaries")
required = [
    "words", "flesch_reading_ease", "word_compression_ratio",
    "gemini_source_alignment_rate", "minicheck_mean_probability",
    "weighted_coverage_rate", "omission_rate",
]
missing = summary[required].isna().sum()
if missing.any():
    raise RuntimeError(f"Missing summary metrics: {missing[missing.gt(0)].to_dict()}")

summary.to_csv(OUT / "opp115_summary_level_metrics.csv", index=False)

metrics = {
    "Flesch Reading Ease": "flesch_reading_ease",
    "Word compression ratio": "word_compression_ratio",
    "Gemini supported-sentence rate": "gemini_source_alignment_rate",
    "Gemini weighted source-alignment rate": "gemini_weighted_alignment_rate",
    "MiniCheck mean support probability": "minicheck_mean_probability",
    "Weighted information coverage": "weighted_coverage_rate",
    "Omission rate": "omission_rate",
    "Distortion rate": "distortion_rate",
    "Hallucination rate": "hallucination_rate",
}

condition_rows = []
for (model, prompt_set, strategy), group in summary.groupby(["model_family", "prompt_set", "prompting_strategy"], sort=False):
    for label, column in metrics.items():
        values = group[column].astype(float)
        condition_rows.append({
            "model": model,
            "prompt_set": prompt_set,
            "prompting_strategy": strategy,
            "metric": label,
            "n": int(values.size),
            "mean": float(values.mean()),
            "sd": float(values.std(ddof=1)),
            "median": float(values.median()),
            "q1": float(values.quantile(0.25)),
            "q3": float(values.quantile(0.75)),
        })
condition = pd.DataFrame(condition_rows)
condition.to_csv(OUT / "condition_descriptive_statistics.csv", index=False)

# Primary prompt-set tests: one paired mean per policy, preserving policy as the unit of analysis.
prompt_tests = []
for label, column in metrics.items():
    policy_means = summary.groupby(["policy_id", "prompt_set"])[column].mean().unstack()
    diff = policy_means["Safety-focused"].to_numpy() - policy_means["Basic"].to_numpy()
    prompt_tests.append(wilcoxon_row(label, "Basic", "Safety-focused", diff, "Prompt set"))
prompt_tests = pd.DataFrame(prompt_tests)
prompt_tests["p_holm_across_metrics"] = holm_adjust(prompt_tests["p_value"].tolist())
prompt_tests.to_csv(OUT / "prompt_set_policy_blocked_tests.csv", index=False)

# Secondary safety-prompt effects for each model and prompting strategy.
cell_tests = []
for label, column in metrics.items():
    start = len(cell_tests)
    for model in MODEL_ORDER:
        for strategy in STRATEGY_ORDER:
            cell = summary[(summary["model_family"] == model) & (summary["prompting_strategy"] == strategy)]
            pivot = cell.pivot(index="policy_id", columns="prompt_set", values=column)
            diff = pivot["Safety-focused"].to_numpy() - pivot["Basic"].to_numpy()
            row = wilcoxon_row(label, "Basic", "Safety-focused", diff, "Prompt set within model × strategy")
            row.update({"model": model, "prompting_strategy": strategy})
            cell_tests.append(row)
    adjusted = holm_adjust([r["p_value"] for r in cell_tests[start:]])
    for row, adj in zip(cell_tests[start:], adjusted):
        row["p_holm_within_metric"] = adj
pd.DataFrame(cell_tests).to_csv(OUT / "prompt_set_cellwise_tests.csv", index=False)


def factorial_block_tests(factor: str, levels: list[str], family: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    omnibus_rows = []
    pair_rows = []
    for label, column in metrics.items():
        block = summary.groupby(["policy_id", factor])[column].mean().unstack()
        block = block[levels]
        friedman_statistic, friedman_p = friedman_three_level(block[levels].to_numpy())
        omnibus_rows.append({
            "family": family,
            "metric": label,
            "n_policies": int(len(block)),
            "levels": " | ".join(levels),
            "friedman_chi_square": friedman_statistic,
            "df": len(levels) - 1,
            "p_value": friedman_p,
            "kendalls_w": float(friedman_statistic / (len(block) * (len(levels) - 1))),
        })
        metric_pairs = []
        for i in range(len(levels)):
            for j in range(i + 1, len(levels)):
                diff = block[levels[j]].to_numpy() - block[levels[i]].to_numpy()
                row = wilcoxon_row(label, levels[i], levels[j], diff, family + " pairwise")
                row.update({"level_1": levels[i], "level_2": levels[j]})
                metric_pairs.append(row)
        adjusted = holm_adjust([r["p_value"] for r in metric_pairs])
        for row, adj in zip(metric_pairs, adjusted):
            row["p_holm_within_metric"] = adj
        pair_rows.extend(metric_pairs)
    omnibus = pd.DataFrame(omnibus_rows)
    omnibus["p_holm_across_metrics"] = holm_adjust(omnibus["p_value"].tolist())
    return omnibus, pd.DataFrame(pair_rows)


model_omnibus, model_pairs = factorial_block_tests("model_family", MODEL_ORDER, "Model family")
strategy_omnibus, strategy_pairs = factorial_block_tests("prompting_strategy", STRATEGY_ORDER, "Prompting strategy")
model_omnibus.to_csv(OUT / "model_friedman_tests.csv", index=False)
model_pairs.to_csv(OUT / "model_pairwise_tests.csv", index=False)
strategy_omnibus.to_csv(OUT / "strategy_friedman_tests.csv", index=False)
strategy_pairs.to_csv(OUT / "strategy_pairwise_tests.csv", index=False)

# Raw, easily interpretable failure and omission totals by prompt set.
gemini_with_set = gemini.merge(key[["blind_id", "prompt_set"]], on="blind_id", validate="many_to_one")
failure_table = pd.crosstab(gemini_with_set["prompt_set"], gemini_with_set["label"]).reindex(SET_ORDER, fill_value=0)
failure_table["Total claims"] = failure_table.sum(axis=1)
for col in [c for c in failure_table.columns if c != "Total claims"]:
    failure_table[f"{col} rate"] = failure_table[col] / failure_table["Total claims"]
failure_table.reset_index().to_csv(OUT / "claim_failure_counts_by_prompt_set.csv", index=False)

coverage_with_set = coverage.merge(key[["blind_id", "prompt_set"]], on="blind_id", validate="many_to_one")
omission_table = pd.crosstab(coverage_with_set["prompt_set"], coverage_with_set["coverage_label"]).reindex(SET_ORDER, fill_value=0)
omission_table["Total comparisons"] = omission_table.sum(axis=1)
for col in [c for c in omission_table.columns if c != "Total comparisons"]:
    omission_table[f"{col} rate"] = omission_table[col] / omission_table["Total comparisons"]
omission_table.reset_index().to_csv(OUT / "coverage_counts_by_prompt_set.csv", index=False)

audit = {
    "status": "pass",
    "summaries": int(len(summary)),
    "policies": int(summary["policy_id"].nunique()),
    "claims_gemini": int(len(gemini)),
    "claims_minicheck": int(len(minicheck)),
    "coverage_comparisons": int(len(coverage)),
    "source_units": int(coverage["unit_id"].nunique()),
    "missing_required_metrics": {k: int(v) for k, v in missing.items()},
    "duplicate_summary_ids": int(summary["blind_id"].duplicated().sum()),
    "analysis_unit": "policy (n=27) for inferential tests",
    "primary_tests": "Wilcoxon signed-rank for prompt set; Friedman tests for model and prompting strategy",
    "multiple_testing": "Holm adjustment within stated metric families",
    "bootstrap_seed": 20260830,
}
(OUT / "analysis_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")


def fmt_p(value: float) -> str:
    return "< .001" if value < 0.001 else f"= {value:.3f}"


lines = [
    "# OPP extension: policy-blocked statistical analysis",
    "",
    "The analysis treats each of the 27 policies as the inferential unit. This avoids treating the 486 summaries or their individual sentences as statistically independent observations.",
    "",
    "## Prompt-set effects",
    "",
]
for _, row in prompt_tests.iterrows():
    direction = "increased" if row["mean_difference"] > 0 else "decreased"
    lines.append(
        f"- {row['metric']}: safety-focused prompting {direction} the policy-level mean by {abs(row['mean_difference']):.4f} "
        f"(95% bootstrap CI {row['bootstrap_95ci_low']:.4f} to {row['bootstrap_95ci_high']:.4f}; "
        f"Wilcoxon p {fmt_p(row['p_value'])}; Holm-adjusted p {fmt_p(row['p_holm_across_metrics'])}; "
        f"rank-biserial {row['rank_biserial']:.3f})."
    )
lines.extend(["", "## Model-family omnibus tests", ""])
for _, row in model_omnibus.iterrows():
    lines.append(
        f"- {row['metric']}: Friedman χ²({int(row['df'])})={row['friedman_chi_square']:.3f}, "
        f"p {fmt_p(row['p_value'])}, Holm-adjusted p {fmt_p(row['p_holm_across_metrics'])}, Kendall's W={row['kendalls_w']:.3f}."
    )
lines.extend(["", "## Prompting-strategy omnibus tests", ""])
for _, row in strategy_omnibus.iterrows():
    lines.append(
        f"- {row['metric']}: Friedman χ²({int(row['df'])})={row['friedman_chi_square']:.3f}, "
        f"p {fmt_p(row['p_value'])}, Holm-adjusted p {fmt_p(row['p_holm_across_metrics'])}, Kendall's W={row['kendalls_w']:.3f}."
    )
(OUT / "statistical_analysis_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps(audit, indent=2))
