from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "data" / "opp115" / "experiment"
SCORES = EXP / "coverage_v3" / "evaluations" / "gemini_coverage_scores.csv"
UNITS = EXP / "coverage_v3" / "source_units" / "frozen_source_units.csv"
KEY = EXP / "anonymised" / "BLINDING_KEY_RESTRICTED.csv"
OUT = EXP / "coverage_v3" / "analysis"
OUT.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def descriptive(frame: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    metrics = [
        "strict_coverage_rate", "weighted_coverage_rate",
        "partial_coverage_rate", "omission_rate",
    ]
    grouped = frame.groupby(groups, dropna=False, sort=True) if groups else [((), frame)]
    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        identity = dict(zip(groups, key))
        for metric in metrics:
            values = group[metric].astype(float)
            rows.append({
                **identity,
                "metric": metric,
                "n_summaries": int(len(values)),
                "mean": float(values.mean()),
                "sd": float(values.std(ddof=1)) if len(values) > 1 else None,
                "median": float(values.median()),
                "q1": float(values.quantile(0.25)),
                "q3": float(values.quantile(0.75)),
                "minimum": float(values.min()),
                "maximum": float(values.max()),
            })
    return pd.DataFrame(rows)


def main() -> None:
    scores = pd.read_csv(SCORES, dtype={"blind_id": str, "unit_id": str})
    units = pd.read_csv(UNITS, dtype={"policy_id": str, "unit_id": str})
    key = pd.read_csv(KEY, dtype={"blind_id": str, "policy_id": str})
    errors: list[str] = []

    if len(scores) != 18144:
        errors.append(f"Expected 18144 score rows, found {len(scores)}")
    if scores["comparison_id"].duplicated().any():
        errors.append("Duplicate comparison IDs")
    if not scores["status"].eq("success").all():
        errors.append("Non-success score rows")
    allowed = {"Covered", "Partially covered", "Not covered"}
    invalid = sorted(set(scores["coverage_label"]) - allowed)
    if invalid:
        errors.append(f"Invalid coverage labels: {invalid}")
    if len(key) != 486 or key["blind_id"].nunique() != 486:
        errors.append("Blinding key does not contain 486 unique summaries")
    if len(units) != 1008 or units["unit_id"].nunique() != 1008:
        errors.append("Frozen unit set does not contain 1008 unique units")

    scores["is_covered"] = scores["coverage_label"].eq("Covered").astype(int)
    scores["is_partial"] = scores["coverage_label"].eq("Partially covered").astype(int)
    scores["is_omitted"] = scores["coverage_label"].eq("Not covered").astype(int)
    metrics = scores.groupby("blind_id", as_index=False).agg(
        policy_id_from_scores=("policy_id", "first"),
        source_unit_count=("unit_id", "nunique"),
        covered_units=("is_covered", "sum"),
        partially_covered_units=("is_partial", "sum"),
        omitted_units=("is_omitted", "sum"),
    )
    metrics["strict_coverage_rate"] = metrics["covered_units"] / metrics["source_unit_count"]
    metrics["weighted_coverage_rate"] = (
        metrics["covered_units"] + 0.5 * metrics["partially_covered_units"]
    ) / metrics["source_unit_count"]
    metrics["partial_coverage_rate"] = metrics["partially_covered_units"] / metrics["source_unit_count"]
    metrics["omission_rate"] = metrics["omitted_units"] / metrics["source_unit_count"]

    key[["prompt_set", "prompting_strategy"]] = key["prompt_strategy"].apply(
        lambda value: pd.Series(prompt_labels(value))
    )
    summary = key.merge(metrics, on="blind_id", how="left", validate="one_to_one")
    if summary["source_unit_count"].isna().any():
        errors.append("Missing coverage profile after blinding-key merge")
    if not summary["policy_id"].eq(summary["policy_id_from_scores"]).all():
        errors.append("Policy mismatch between blinding key and coverage results")

    unit_counts = units.groupby("policy_id")["unit_id"].nunique()
    expected_counts = summary["policy_id"].map(unit_counts)
    if not summary["source_unit_count"].eq(expected_counts).all():
        errors.append("At least one summary does not contain every unit from its policy")
    if not (
        summary["covered_units"]
        + summary["partially_covered_units"]
        + summary["omitted_units"]
    ).eq(summary["source_unit_count"]).all():
        errors.append("Coverage label counts do not reconcile to source-unit totals")

    pair_key = ["policy_id", "model_family", "prompting_strategy"]
    pair_sizes = summary.groupby(pair_key)["prompt_set"].nunique()
    if len(pair_sizes) != 243 or not pair_sizes.eq(2).all():
        errors.append("Expected 243 complete Basic/Safety-focused matched pairs")

    summary = summary.drop(columns=["policy_id_from_scores"])
    summary.to_csv(OUT / "opp115_v3_coverage_by_summary.csv", index=False, encoding="utf-8-sig")

    descriptive(summary, []).to_csv(
        OUT / "coverage_overall_descriptive.csv", index=False, encoding="utf-8-sig"
    )
    descriptive(summary, ["prompt_set"]).to_csv(
        OUT / "coverage_by_prompt_set.csv", index=False, encoding="utf-8-sig"
    )
    descriptive(summary, ["model_family"]).to_csv(
        OUT / "coverage_by_model.csv", index=False, encoding="utf-8-sig"
    )
    descriptive(summary, ["prompting_strategy"]).to_csv(
        OUT / "coverage_by_strategy.csv", index=False, encoding="utf-8-sig"
    )
    descriptive(summary, ["model_family", "prompting_strategy", "prompt_set"]).to_csv(
        OUT / "coverage_by_full_condition.csv", index=False, encoding="utf-8-sig"
    )

    pair_rows: list[dict] = []
    for metric in ["strict_coverage_rate", "weighted_coverage_rate", "omission_rate"]:
        pivot = summary.pivot(
            index=pair_key, columns="prompt_set", values=metric
        ).reset_index()
        pivot["metric"] = metric
        pivot["safety_minus_basic"] = pivot["Safety-focused"] - pivot["Basic"]
        pair_rows.extend(pivot.to_dict("records"))
    pairs = pd.DataFrame(pair_rows)
    pairs.to_csv(OUT / "matched_basic_safety_differences.csv", index=False, encoding="utf-8-sig")

    delta_rows: list[dict] = []
    for metric, group in pairs.groupby("metric", sort=True):
        delta = group["safety_minus_basic"].astype(float)
        higher_is_better = metric != "omission_rate"
        improved = delta.gt(0) if higher_is_better else delta.lt(0)
        worsened = delta.lt(0) if higher_is_better else delta.gt(0)
        delta_rows.append({
            "metric": metric,
            "desirable_direction": "higher" if higher_is_better else "lower",
            "matched_pairs": int(len(delta)),
            "mean_difference": float(delta.mean()),
            "median_difference": float(delta.median()),
            "q1_difference": float(delta.quantile(0.25)),
            "q3_difference": float(delta.quantile(0.75)),
            "improved_pairs": int(improved.sum()),
            "unchanged_pairs": int(delta.eq(0).sum()),
            "worsened_pairs": int(worsened.sum()),
        })
    delta_summary = pd.DataFrame(delta_rows)
    delta_summary.to_csv(
        OUT / "matched_basic_safety_descriptive.csv", index=False, encoding="utf-8-sig"
    )

    audit = {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "raw_comparisons": int(len(scores)),
        "summaries": int(len(summary)),
        "policies": int(summary["policy_id"].nunique()),
        "source_units": int(units["unit_id"].nunique()),
        "matched_basic_safety_pairs": int(len(pair_sizes)),
        "source_sha256": {
            "coverage_scores": sha256(SCORES),
            "frozen_units": sha256(UNITS),
            "blinding_key": sha256(KEY),
        },
        "score_definitions": {
            "strict_coverage": "Covered / all source units",
            "weighted_coverage": "(Covered + 0.5 * Partially covered) / all source units",
            "omission_rate": "Not covered / all source units",
        },
    }
    (OUT / "summary_level_coverage_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
