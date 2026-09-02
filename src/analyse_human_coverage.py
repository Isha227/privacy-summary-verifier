from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .common import ROOT


BASE = ROOT / "data/main/coverage_validation/MAIN17"
HUMAN_DIR = BASE / "human_validation"
RESULTS_DIR = BASE / "evaluations/human_validation_results"
LABELS = (0, 1, 2)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to write an empty result: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _confusion(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    matrix = np.zeros((3, 3), dtype=int)
    for a, b in zip(left, right):
        matrix[int(a), int(b)] += 1
    return matrix


def _kappa(left: np.ndarray, right: np.ndarray, weighted: bool = False) -> float:
    matrix = _confusion(left, right).astype(float)
    observed = matrix / matrix.sum()
    expected = np.outer(matrix.sum(axis=1), matrix.sum(axis=0)) / matrix.sum() ** 2
    if weighted:
        weights = np.fromfunction(lambda i, j: ((i - j) / 2) ** 2, (3, 3))
        denominator = float((weights * expected).sum())
        return 1.0 if denominator == 0 else 1.0 - float((weights * observed).sum()) / denominator
    po = float(np.trace(observed))
    pe = float(np.trace(expected))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _agreement(left: np.ndarray, right: np.ndarray) -> dict:
    difference = np.abs(left - right)
    return {
        "n": int(len(left)),
        "exact_agreement": float(np.mean(left == right)),
        "within_one_category": float(np.mean(difference <= 1)),
        "mean_absolute_difference": float(np.mean(difference)),
        "cohen_kappa": float(_kappa(left, right)),
        "quadratic_weighted_kappa": float(_kappa(left, right, weighted=True)),
    }


def _fleiss_kappa(score_frame: pd.DataFrame) -> float:
    counts = np.stack([(score_frame == label).sum(axis=1).to_numpy() for label in LABELS], axis=1)
    n_raters = score_frame.shape[1]
    p_item = (np.square(counts).sum(axis=1) - n_raters) / (n_raters * (n_raters - 1))
    p_bar = float(p_item.mean())
    category_prevalence = counts.sum(axis=0) / counts.sum()
    p_expected = float(np.square(category_prevalence).sum())
    return 1.0 if p_expected == 1 else (p_bar - p_expected) / (1 - p_expected)


def analyse() -> tuple[int, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ratings = {
        annotator: pd.read_excel(
            HUMAN_DIR / f"human_coverage_{annotator}_COMPLETED.xlsx", sheet_name="Ratings"
        ).set_index("sample_id")
        for annotator in ("A1", "A2", "A3")
    }
    score_frame = pd.DataFrame(
        {annotator: data["human_score"].astype(int) for annotator, data in ratings.items()}
    ).sort_index()
    if score_frame.shape != (180, 3) or score_frame.isna().any().any():
        raise ValueError(f"Expected a complete 180 x 3 human score matrix; found {score_frame.shape}")
    if not set(np.unique(score_frame.to_numpy())).issubset(LABELS):
        raise ValueError("Human scores must be restricted to 0, 1 and 2")

    adjudication = pd.read_excel(
        HUMAN_DIR / "MAIN17_Human_Coverage_Adjudication.xlsx", sheet_name="Adjudication"
    ).set_index("sample_id")
    disagreements = score_frame[score_frame.nunique(axis=1) > 1]
    if set(adjudication.index) != set(disagreements.index):
        raise ValueError("Adjudication rows do not exactly match the independently scored disagreements")
    if not (adjudication["status"] == "Complete").all():
        raise ValueError("Coverage adjudication is incomplete")

    consensus = score_frame["A1"].copy()
    consensus.loc[adjudication.index] = adjudication["final_score"].astype(int)
    resolution = pd.Series("unanimous", index=consensus.index)
    resolution.loc[adjudication.index] = "adjudicated"

    gemini_all = pd.read_csv(BASE / "evaluations/gemini_coverage_scores__gemini-3.5-flash-lite.csv")
    sample_index = ratings["A1"].reset_index()[["sample_id", "blind_id", "unit_id", "category"]]
    sample = sample_index.merge(
        gemini_all[["blind_id", "unit_id", "coverage_score", "status"]],
        on=["blind_id", "unit_id"], how="left", validate="one_to_one",
    ).set_index("sample_id").loc[score_frame.index]
    if sample["coverage_score"].isna().any() or not (sample["status"] == "success").all():
        raise ValueError("Gemini does not contain 180 successful scores for the frozen human sample")
    gemini = sample["coverage_score"].astype(int)

    pairwise_rows: list[dict] = []
    for left, right in (("A1", "A2"), ("A1", "A3"), ("A2", "A3")):
        metrics = _agreement(score_frame[left].to_numpy(), score_frame[right].to_numpy())
        pairwise_rows.append({"comparison": f"{left} vs {right}", **metrics})
    _write_csv(RESULTS_DIR / "human_pairwise_agreement.csv", pairwise_rows)

    all_three = int((score_frame.nunique(axis=1) == 1).sum())
    human_summary = [
        {"measure": "sampled comparisons", "value": len(score_frame)},
        {"measure": "all-three exact agreements", "value": all_three},
        {"measure": "all-three exact agreement proportion", "value": all_three / len(score_frame)},
        {"measure": "rows adjudicated", "value": len(adjudication)},
        {"measure": "adjudicated scores departing from majority", "value": int((adjudication.final_score != adjudication.majority_score).sum())},
        {"measure": "Fleiss kappa (three raters; nominal)", "value": _fleiss_kappa(score_frame)},
    ]
    _write_csv(RESULTS_DIR / "human_overall_agreement.csv", human_summary)

    gemini_metrics = _agreement(consensus.to_numpy(), gemini.to_numpy())
    gemini_rows = [{"comparison": "Gemini vs final human consensus", **gemini_metrics}]
    _write_csv(RESULTS_DIR / "gemini_human_agreement_overall.csv", gemini_rows)

    by_category: list[dict] = []
    for category in sorted(sample["category"].unique()):
        ids = sample.index[sample["category"] == category]
        by_category.append({
            "category": category,
            **_agreement(consensus.loc[ids].to_numpy(), gemini.loc[ids].to_numpy()),
        })
    _write_csv(RESULTS_DIR / "gemini_human_agreement_by_category.csv", by_category)

    confusion = _confusion(consensus.to_numpy(), gemini.to_numpy())
    confusion_rows = [
        {
            "human_final_score": human_label,
            "gemini_score_0": int(confusion[human_label, 0]),
            "gemini_score_1": int(confusion[human_label, 1]),
            "gemini_score_2": int(confusion[human_label, 2]),
            "row_total": int(confusion[human_label].sum()),
        }
        for human_label in LABELS
    ]
    _write_csv(RESULTS_DIR / "gemini_human_confusion_matrix.csv", confusion_rows)

    final_rows = []
    for sample_id in score_frame.index:
        final_rows.append({
            "sample_id": sample_id,
            "blind_id": sample.loc[sample_id, "blind_id"],
            "unit_id": sample.loc[sample_id, "unit_id"],
            "category": sample.loc[sample_id, "category"],
            "A1_score": int(score_frame.loc[sample_id, "A1"]),
            "A2_score": int(score_frame.loc[sample_id, "A2"]),
            "A3_score": int(score_frame.loc[sample_id, "A3"]),
            "final_human_score": int(consensus.loc[sample_id]),
            "resolution": resolution.loc[sample_id],
            "gemini_score": int(gemini.loc[sample_id]),
            "exact_match": int(consensus.loc[sample_id] == gemini.loc[sample_id]),
            "absolute_difference": int(abs(consensus.loc[sample_id] - gemini.loc[sample_id])),
        })
    _write_csv(RESULTS_DIR / "human_consensus_and_gemini_sample.csv", final_rows)

    distributions = {
        annotator: {str(k): int(v) for k, v in Counter(score_frame[annotator]).items()}
        for annotator in score_frame
    }
    distributions["final_human_consensus"] = {str(k): int(v) for k, v in Counter(consensus).items()}
    distributions["gemini"] = {str(k): int(v) for k, v in Counter(gemini).items()}
    summary = {
        "sample_size": len(score_frame),
        "summaries": int(sample["blind_id"].nunique()),
        "categories": int(sample["category"].nunique()),
        "unanimous_rows": all_three,
        "all_three_exact_agreement": all_three / len(score_frame),
        "disagreement_rows": len(adjudication),
        "adjudication_departures_from_majority": int((adjudication.final_score != adjudication.majority_score).sum()),
        "fleiss_kappa": _fleiss_kappa(score_frame),
        "pairwise": pairwise_rows,
        "gemini_vs_final_human": gemini_metrics,
        "score_distributions": distributions,
    }
    (RESULTS_DIR / "coverage_validation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    exact_pct = 100 * gemini_metrics["exact_agreement"]
    report = f"""# MAIN17 human coverage-validation results

The frozen validation sample contained 180 unit-summary comparisons, comprising 20 comparisons from each of nine blinded summaries and representing all nine coverage categories. The three researchers assigned the same score to {all_three} comparisons ({100 * all_three / len(score_frame):.1f}%). Pairwise exact agreement ranged from {100 * min(r['exact_agreement'] for r in pairwise_rows):.1f}% to {100 * max(r['exact_agreement'] for r in pairwise_rows):.1f}%, while quadratic weighted Cohen's kappa ranged from {min(r['quadratic_weighted_kappa'] for r in pairwise_rows):.3f} to {max(r['quadratic_weighted_kappa'] for r in pairwise_rows):.3f}. Fleiss' kappa across all three researchers was {_fleiss_kappa(score_frame):.3f}. The remaining {len(adjudication)} comparisons were adjudicated after independent scoring; the final decision differed from the two-person majority on {int((adjudication.final_score != adjudication.majority_score).sum())} rows.

Gemini exactly matched the final human score on {int((consensus.to_numpy() == gemini.to_numpy()).sum())} of 180 comparisons ({exact_pct:.1f}%). Quadratic weighted Cohen's kappa between Gemini and the final human score was {gemini_metrics['quadratic_weighted_kappa']:.3f}, and the mean absolute difference on the 0-2 scale was {gemini_metrics['mean_absolute_difference']:.3f}. These results support using Gemini as an automated coverage measure for the MAIN17 experiment while retaining the observed disagreement as a measurement limitation; they do not establish that Gemini is ground truth or that validation generalises beyond this policy and sample.
"""
    report_path = RESULTS_DIR / "coverage_validation_report_ready.md"
    report_path.write_text(report, encoding="utf-8")
    return len(score_frame), report_path


if __name__ == "__main__":
    count, path = analyse()
    print(f"Analysed {count} human coverage comparisons: {path}")
