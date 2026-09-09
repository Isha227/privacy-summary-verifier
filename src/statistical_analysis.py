from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "combined_30_policy_statistics"
OUT.mkdir(parents=True, exist_ok=True)

OPP_READ = ROOT / "data/opp115/experiment/evaluations/readability_compression.csv"
OPP_KEY = ROOT / "data/opp115/experiment/anonymised/BLINDING_KEY_RESTRICTED.csv"
OPP_GEM = ROOT / "data/opp115/experiment/evaluations/faithfulness/gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"
OPP_MINI = ROOT / "data/opp115/experiment/evaluations/faithfulness/minicheck_opp115_claim_scores_FINAL.csv"
OPP_COV = ROOT / "data/opp115/experiment/coverage_v3/analysis/opp115_v3_coverage_by_summary.csv"
CURRENT = ROOT / "outputs/v12_final_analysis/v12_automated_summary_level.csv"

OUTCOMES = {
    "Reading Ease": "flesch_reading_ease",
    "Source text retained": "word_compression_ratio",
    "Gemini support rate": "gemini_support_rate",
    "Gemini weighted alignment": "gemini_weighted_alignment",
    "Weighted coverage": "coverage_weighted_rate",
    "Omission": "omission_rate",
    "Distortion": "distortion_rate",
    "Hallucination": "hallucination_rate",
    "MiniCheck support probability": "minicheck_mean_probability",
}


def holm(pvalues: pd.Series) -> pd.Series:
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * p[idx])
        running = max(running, value)
        adjusted[idx] = running
    return pd.Series(adjusted, index=pvalues.index)


def rankdata(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return ranks


def friedman_test(arrays: list[np.ndarray]) -> tuple[float, float]:
    matrix = np.column_stack(arrays).astype(float)
    n, k = matrix.shape
    row_ranks = np.vstack([rankdata(row) for row in matrix])
    rank_sums = row_ranks.sum(axis=0)
    q = (12.0 / (n * k * (k + 1))) * np.sum(rank_sums ** 2) - 3 * n * (k + 1)
    tie_sum = 0.0
    for row in matrix:
        _, counts = np.unique(row, return_counts=True)
        tie_sum += np.sum(counts ** 3 - counts)
    correction = 1.0 - tie_sum / (n * (k ** 3 - k))
    if correction > 0:
        q /= correction
    # Every requested Friedman comparison has k=3, hence df=2 and
    # the chi-square survival function is exactly exp(-q/2).
    p = math.exp(-q / 2.0)
    return float(q), float(p)


def wilcoxon_signed_rank(diff: np.ndarray) -> tuple[float, float]:
    values = np.asarray(diff, dtype=float)
    values = values[np.isfinite(values) & (values != 0)]
    if len(values) == 0:
        return 0.0, 1.0
    abs_values = np.abs(values)
    ranks = rankdata(abs_values)
    w_pos = float(ranks[values > 0].sum())
    w_neg = float(ranks[values < 0].sum())
    w = min(w_pos, w_neg)
    n = len(values)
    _, counts = np.unique(abs_values, return_counts=True)
    tie_term = float(np.sum(counts ** 3 - counts))
    mean = n * (n + 1) / 4.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0 - tie_term / 48.0
    z = (w - mean) / math.sqrt(variance)
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return w, p


def aggregate_opp() -> pd.DataFrame:
    read = pd.read_csv(OPP_READ)
    key = pd.read_csv(OPP_KEY)
    cov = pd.read_csv(OPP_COV)
    gem = pd.read_csv(OPP_GEM)
    mini = pd.read_csv(OPP_MINI)

    g = gem.assign(
        is_supported=(gem["label"] == "Supported").astype(int),
        alignment_weight=gem["label"].map({"Supported": 1.0, "Partially supported": 0.5, "Unsupported": 0.0, "Contradicted": 0.0}),
        is_distortion=(gem["label"] == "Partially supported").astype(int),
        is_hallucination=gem["label"].isin(["Unsupported", "Contradicted"]).astype(int),
    ).groupby("blind_id", as_index=False).agg(
        gemini_statements=("claim_id", "count"),
        gemini_supported=("is_supported", "sum"),
        gemini_support_rate=("is_supported", "mean"),
        gemini_weighted_alignment=("alignment_weight", "mean"),
        distortion_rate=("is_distortion", "mean"),
        hallucination_rate=("is_hallucination", "mean"),
    )
    m = mini.groupby("blind_id", as_index=False).agg(
        minicheck_mean_probability=("support_probability", "mean"),
        minicheck_support_rate=("predicted_supported", "mean"),
    )
    result = read.merge(key, on=["run_id", "policy_id", "model_family", "prompt_strategy", "replicate"], validate="one_to_one")
    result = result.merge(g, on="blind_id", validate="one_to_one").merge(m, on="blind_id", validate="one_to_one")
    result = result.merge(
        cov[["blind_id", "weighted_coverage_rate", "omission_rate"]], on="blind_id", validate="one_to_one"
    ).rename(columns={"weighted_coverage_rate": "coverage_weighted_rate"})
    result["prompt_set"] = np.where(result["prompt_strategy"].str.startswith("safety_focused"), "safety_focused", "basic")
    result["strategy"] = result["prompt_strategy"].str.replace("safety_focused_", "", regex=False).str.replace("basic_", "", regex=False)
    result["corpus"] = "OPP-115"
    return result


def prepare_current() -> pd.DataFrame:
    cur = pd.read_csv(CURRENT)
    cur["gemini_weighted_alignment"] = (cur["gemini_supported"] + 0.5 * cur["gemini_partial"]) / cur["gemini_statements"]
    cur["distortion_rate"] = cur["gemini_distortion"] / cur["gemini_statements"]
    cur["hallucination_rate"] = cur["gemini_hallucination"] / cur["gemini_statements"]
    cur["omission_rate"] = cur["coverage_not_covered"] / cur["coverage_units"]
    cur["corpus"] = "Contemporary"
    return cur


def friedman_effects(data: pd.DataFrame, factor: str, levels: list[str]) -> pd.DataFrame:
    rows = []
    for outcome, col in OUTCOMES.items():
        means = data.groupby(["policy_id", factor], as_index=False)[col].mean()
        wide = means.pivot(index="policy_id", columns=factor, values=col).dropna(subset=levels)
        stat, p = friedman_test([wide[level].to_numpy() for level in levels])
        rows.append({"outcome": outcome, "n_policy_blocks": len(wide), "chi_square": stat, "df": len(levels)-1, "p_raw": p})
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out["p_raw"])
    return out


def rank_biserial(diff: np.ndarray) -> float:
    nz = diff[np.isfinite(diff) & (diff != 0)]
    if len(nz) == 0:
        return 0.0
    ranks = rankdata(np.abs(nz))
    pos = ranks[nz > 0].sum()
    neg = ranks[nz < 0].sum()
    return float((pos - neg) / (pos + neg))


def paired_effects(data: pd.DataFrame, seed: int = 20260903, n_boot: int = 10000) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["policy_id", "model_family", "strategy"]
    rows, deltas = [], []
    rng = np.random.default_rng(seed)
    for outcome, col in OUTCOMES.items():
        wide = data.pivot(index=keys, columns="prompt_set", values=col).dropna(subset=["basic", "safety_focused"])
        diff = (wide["safety_focused"] - wide["basic"]).to_numpy(dtype=float)
        boot = rng.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
        stat, p = wilcoxon_signed_rank(diff)
        rows.append({
            "outcome": outcome,
            "n_pairs": len(diff),
            "mean_basic": float(wide["basic"].mean()),
            "mean_safety": float(wide["safety_focused"].mean()),
            "mean_change": float(diff.mean()),
            "ci95_low": float(np.quantile(boot, 0.025)),
            "ci95_high": float(np.quantile(boot, 0.975)),
            "wilcoxon_w": stat,
            "p_raw": p,
            "rank_biserial": rank_biserial(diff),
        })
        part = wide.reset_index()
        part["outcome"] = outcome
        part["difference_safety_minus_basic"] = diff
        deltas.append(part)
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out["p_raw"])
    return out, pd.concat(deltas, ignore_index=True)


def main() -> None:
    opp = aggregate_opp()
    cur = prepare_current()
    keep = ["blind_id", "run_id", "policy_id", "model_family", "prompt_strategy", "prompt_set", "strategy", "corpus"] + list(OUTCOMES.values())
    combined = pd.concat([opp[keep], cur[keep]], ignore_index=True)
    assert len(combined) == 540, len(combined)
    assert combined["policy_id"].nunique() == 30
    assert not combined.duplicated(["policy_id", "model_family", "strategy", "prompt_set"]).any()
    assert not combined[list(OUTCOMES.values())].isna().any().any()

    desc = combined.groupby("model_family", as_index=False).agg(
        n_summaries=("blind_id", "count"),
        mean_reading_ease=("flesch_reading_ease", "mean"),
        mean_source_text_retained=("word_compression_ratio", "mean"),
        mean_gemini_supported=("gemini_support_rate", "mean"),
        mean_gemini_weighted_alignment=("gemini_weighted_alignment", "mean"),
        mean_weighted_coverage=("coverage_weighted_rate", "mean"),
        mean_omission=("omission_rate", "mean"),
        mean_distortion=("distortion_rate", "mean"),
        mean_hallucination=("hallucination_rate", "mean"),
        mean_minicheck_probability=("minicheck_mean_probability", "mean"),
    )
    model = friedman_effects(combined, "model_family", ["gpt", "llama", "mistral"])
    strategy = friedman_effects(combined, "strategy", ["direct", "role_guided", "structured"])
    paired, deltas = paired_effects(combined)

    combined.to_csv(OUT / "combined_540_summary_level.csv", index=False)
    desc.to_csv(OUT / "table2_descriptive_by_model.csv", index=False)
    model.to_csv(OUT / "friedman_model_effects_30_blocks.csv", index=False)
    strategy.to_csv(OUT / "friedman_prompting_effects_30_blocks.csv", index=False)
    paired.to_csv(OUT / "table3_basic_to_safety_wilcoxon_270_pairs.csv", index=False)
    deltas.to_csv(OUT / "paired_differences_270_conditions.csv", index=False)
    audit = {
        "summaries": len(combined), "policies": combined.policy_id.nunique(),
        "models": combined.model_family.value_counts().to_dict(),
        "strategies": combined.strategy.value_counts().to_dict(),
        "prompt_sets": combined.prompt_set.value_counts().to_dict(),
        "paired_conditions": int(paired.n_pairs.unique()[0]),
        "duplicates": int(combined.duplicated(["policy_id", "model_family", "strategy", "prompt_set"]).sum()),
        "missing_outcome_cells": int(combined[list(OUTCOMES.values())].isna().sum().sum()),
        "bootstrap_seed": 20260903, "bootstrap_resamples": 10000,
    }
    (OUT / "analysis_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    print("\nDESCRIPTIVE\n", desc.to_string(index=False))
    print("\nMODEL FRIEDMAN\n", model.to_string(index=False))
    print("\nSTRATEGY FRIEDMAN\n", strategy.to_string(index=False))
    print("\nPAIRED\n", paired.to_string(index=False))


if __name__ == "__main__":
    main()
