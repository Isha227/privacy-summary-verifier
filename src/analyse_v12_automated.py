from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .common import ROOT


BASE = ROOT / "data/v2_prompt_intervention_v1_2"
EVAL = BASE / "evaluations"
OUT = ROOT / "outputs/v12_final_analysis"


def _split_prompt(frame: pd.DataFrame) -> pd.DataFrame:
    parts = frame["prompt_strategy"].str.extract(r"^(basic|safety_focused)_(direct|role_guided|structured)$")
    frame = frame.copy()
    frame["prompt_set"], frame["strategy"] = parts[0], parts[1]
    return frame


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = _split_prompt(pd.read_csv(EVAL / "readability_compression.csv"))
    key = _split_prompt(pd.read_csv(BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv"))
    gemini = pd.read_csv(EVAL / "gemini_statement_verification_all.csv", keep_default_na=False)
    minicheck = pd.read_csv(EVAL / "minicheck/minicheck_v12_statement_scores_FINAL.csv")
    coverage = pd.read_csv(EVAL / "gemini_preliminary_coverage_all.csv", keep_default_na=False)

    g = gemini.groupby("blind_id").agg(
        gemini_statements=("statement_id", "size"),
        gemini_supported=("label", lambda s: int((s == "Supported").sum())),
        gemini_partial=("label", lambda s: int((s == "Partially supported").sum())),
        gemini_unsupported=("label", lambda s: int((s == "Unsupported").sum())),
        gemini_contradicted=("label", lambda s: int((s == "Contradicted").sum())),
        gemini_distortion=("failure_type", lambda s: int(s.str.contains("Distortion", case=False).sum())),
        gemini_hallucination=("failure_type", lambda s: int(s.str.contains("Hallucination", case=False).sum())),
    ).reset_index()
    g["gemini_support_rate"] = g["gemini_supported"] / g["gemini_statements"]

    m = minicheck.groupby("blind_id").agg(
        minicheck_statements=("statement_id", "size"),
        minicheck_supported=("predicted_supported", "sum"),
        minicheck_mean_probability=("probability", "mean"),
    ).reset_index()
    m["minicheck_support_rate"] = m["minicheck_supported"] / m["minicheck_statements"]

    c = coverage.groupby("blind_id").agg(
        coverage_units=("proposed_unit_id", "size"),
        coverage_covered=("coverage_label", lambda s: int((s == "Covered").sum())),
        coverage_partial=("coverage_label", lambda s: int((s == "Partially covered").sum())),
        coverage_not_covered=("coverage_label", lambda s: int((s == "Not covered").sum())),
    ).reset_index()
    c["coverage_strict_rate"] = c["coverage_covered"] / c["coverage_units"]
    c["coverage_weighted_rate"] = (c["coverage_covered"] + 0.5 * c["coverage_partial"]) / c["coverage_units"]

    identifiers = key[["blind_id", "run_id", "policy_id", "model_family", "prompt_set", "strategy", "replicate"]]
    summary = identifiers.merge(metrics, on=["run_id", "policy_id", "model_family", "prompt_set", "strategy", "replicate"], validate="one_to_one")
    summary = summary.merge(g, on="blind_id", validate="one_to_one").merge(m, on="blind_id", validate="one_to_one").merge(c, on="blind_id", validate="one_to_one")
    assert len(summary) == 54 and summary["blind_id"].is_unique
    summary.to_csv(OUT / "v12_automated_summary_level.csv", index=False)

    measures = [
        "words", "flesch_reading_ease", "flesch_kincaid_grade", "smog_grade",
        "word_compression_ratio", "gemini_support_rate", "minicheck_support_rate",
        "coverage_strict_rate", "coverage_weighted_rate",
    ]
    condition = summary.groupby(["prompt_set", "model_family", "strategy"])[measures].agg(["mean", "std", "min", "max"])
    condition.columns = [f"{measure}_{stat}" for measure, stat in condition.columns]
    condition.reset_index().to_csv(OUT / "v12_automated_by_condition.csv", index=False)

    index = ["policy_id", "model_family", "strategy"]
    paired = summary.pivot(index=index, columns="prompt_set", values=measures)
    rows = []
    for condition_id, values in paired.iterrows():
        row = dict(zip(index, condition_id))
        for measure in measures:
            basic = float(values[(measure, "basic")])
            safety = float(values[(measure, "safety_focused")])
            row[f"{measure}_basic"] = basic
            row[f"{measure}_safety_focused"] = safety
            row[f"{measure}_delta_safety_minus_basic"] = safety - basic
        rows.append(row)
    deltas = pd.DataFrame(rows)
    assert len(deltas) == 27
    deltas.to_csv(OUT / "v12_paired_intervention_deltas.csv", index=False)

    delta_summary = []
    for measure in measures:
        values = deltas[f"{measure}_delta_safety_minus_basic"]
        delta_summary.append({
            "measure": measure, "matched_pairs": len(values), "mean_delta": values.mean(),
            "median_delta": values.median(), "min_delta": values.min(), "max_delta": values.max(),
            "positive_pairs": int((values > 0).sum()), "zero_pairs": int((values == 0).sum()),
            "negative_pairs": int((values < 0).sum()),
        })
    pd.DataFrame(delta_summary).to_csv(OUT / "v12_paired_delta_summary.csv", index=False)

    overall = {
        "summaries": len(summary), "matched_intervention_pairs": len(deltas),
        "gemini_statements": int(gemini.shape[0]), "minicheck_statements": int(minicheck.shape[0]),
        "gemini_coverage_comparisons": int(coverage.shape[0]),
        "human_status": "pending",
    }
    (OUT / "v12_analysis_status.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print(f"Created automated analysis: summaries={len(summary)} matched_pairs={len(deltas)}")


if __name__ == "__main__":
    main()
