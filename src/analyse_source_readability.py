"""Create the source-versus-summary readability evidence required for RQ1."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

from .common import ROOT
from .evaluate import metrics


CLEAN_DIR = ROOT / "data" / "main" / "clean"
METADATA_PATH = ROOT / "data" / "main" / "metadata" / "policies.csv"
SUMMARY_METRICS_PATH = ROOT / "data" / "main" / "evaluations" / "metrics.csv"
GENERATION_LOG_PATH = ROOT / "data" / "main" / "logs" / "generation_log.csv"
OUTPUT_DIR = ROOT / "outputs" / "source_readability"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"No rows to write: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def describe(values: list[float]) -> dict[str, float]:
    return {
        "mean": mean(values),
        "sd": stdev(values) if len(values) > 1 else 0.0,
        "median": median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def normalised_metrics(text: str) -> dict:
    """Remove scrape/layout line breaks before applying the same formulae."""
    return metrics(re.sub(r"\s+", " ", text).strip())


def main() -> None:
    metadata = {row["policy_id"]: row for row in read_rows(METADATA_PATH)}
    summary_rows = read_rows(SUMMARY_METRICS_PATH)
    generation_by_run = {
        row["run_id"]: row
        for row in read_rows(GENERATION_LOG_PATH)
        if row.get("status") == "success"
    }
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in summary_rows:
        grouped[row["policy_id"]].append(row)

    expected = set(metadata)
    if set(grouped) != expected:
        raise RuntimeError(
            f"Policy mismatch: missing={sorted(expected-set(grouped))}, "
            f"unexpected={sorted(set(grouped)-expected)}"
        )
    if any(len(rows) != 9 for rows in grouped.values()):
        counts = {policy_id: len(rows) for policy_id, rows in grouped.items()}
        raise RuntimeError(f"Expected nine summaries per policy: {counts}")

    source_rows: list[dict] = []
    comparison_rows: list[dict] = []
    for policy_id in sorted(expected):
        source_path = CLEAN_DIR / f"{policy_id}.txt"
        source_text = source_path.read_text(encoding="utf-8")
        source = metrics(source_text)
        source_normalised = normalised_metrics(source_text)
        summaries = grouped[policy_id]
        summary_flesch = [float(row["flesch_reading_ease"]) for row in summaries]
        summary_grade = [float(row["flesch_kincaid_grade"]) for row in summaries]
        summary_smog = [float(row["smog_grade"]) for row in summaries]
        summary_words = [int(row["words"]) for row in summaries]
        normalised_summary_metrics = []
        for row in summaries:
            run = generation_by_run.get(row["run_id"])
            if not run:
                raise RuntimeError(f"Run not found in generation log: {row['run_id']}")
            summary_text = (ROOT / run["text_path"]).read_text(encoding="utf-8")
            normalised_summary_metrics.append(normalised_metrics(summary_text))
        normalised_summary_flesch = [
            float(row["flesch_reading_ease"]) for row in normalised_summary_metrics
        ]
        meta = metadata[policy_id]
        source_rows.append({
            "policy_id": policy_id,
            "organisation": meta["organisation"],
            "sector": meta["sector"],
            "source_words": source["words"],
            "source_sentences": source["sentences"],
            "source_flesch_reading_ease": source["flesch_reading_ease"],
            "source_flesch_kincaid_grade": source["flesch_kincaid_grade"],
            "source_smog_grade": source["smog_grade"],
            "normalised_source_sentences": source_normalised["sentences"],
            "normalised_source_flesch_reading_ease": source_normalised["flesch_reading_ease"],
            "normalised_source_flesch_kincaid_grade": source_normalised["flesch_kincaid_grade"],
            "normalised_source_smog_grade": source_normalised["smog_grade"],
        })
        comparison_rows.append({
            "policy_id": policy_id,
            "organisation": meta["organisation"],
            "sector": meta["sector"],
            "source_words": source["words"],
            "mean_summary_words": round(mean(summary_words), 3),
            "mean_word_compression_ratio": round(mean(summary_words) / source["words"], 6),
            "source_flesch_reading_ease": source["flesch_reading_ease"],
            "mean_summary_flesch_reading_ease": round(mean(summary_flesch), 3),
            "flesch_improvement": round(mean(summary_flesch) - float(source["flesch_reading_ease"]), 3),
            "normalised_source_flesch_reading_ease": source_normalised["flesch_reading_ease"],
            "mean_normalised_summary_flesch_reading_ease": round(mean(normalised_summary_flesch), 3),
            "normalised_flesch_improvement": round(
                mean(normalised_summary_flesch)
                - float(source_normalised["flesch_reading_ease"]), 3
            ),
            "source_flesch_kincaid_grade": source["flesch_kincaid_grade"],
            "mean_summary_flesch_kincaid_grade": round(mean(summary_grade), 3),
            "grade_reduction": round(float(source["flesch_kincaid_grade"]) - mean(summary_grade), 3),
            "source_smog_grade": source["smog_grade"],
            "mean_summary_smog_grade": round(mean(summary_smog), 3),
            "smog_reduction": round(float(source["smog_grade"]) - mean(summary_smog), 3),
            "summaries": len(summaries),
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_rows(OUTPUT_DIR / "source_policy_readability.csv", source_rows)
    write_rows(OUTPUT_DIR / "source_summary_comparison_by_policy.csv", comparison_rows)

    all_summary_flesch = [float(row["flesch_reading_ease"]) for row in summary_rows]
    all_summary_grade = [float(row["flesch_kincaid_grade"]) for row in summary_rows]
    source_flesch = [float(row["source_flesch_reading_ease"]) for row in source_rows]
    source_grade = [float(row["source_flesch_kincaid_grade"]) for row in source_rows]
    improvements = [float(row["flesch_improvement"]) for row in comparison_rows]
    normalised_source_flesch = [
        float(row["normalised_source_flesch_reading_ease"]) for row in source_rows
    ]
    normalised_summary_flesch = []
    for row in summary_rows:
        run = generation_by_run[row["run_id"]]
        text = (ROOT / run["text_path"]).read_text(encoding="utf-8")
        normalised_summary_flesch.append(
            float(normalised_metrics(text)["flesch_reading_ease"])
        )
    normalised_improvements = [
        float(row["normalised_flesch_improvement"]) for row in comparison_rows
    ]
    compression = [float(row["mean_word_compression_ratio"]) for row in comparison_rows]
    summary = {
        "source_policies": len(source_rows),
        "generated_summaries": len(summary_rows),
        "source_flesch": describe(source_flesch),
        "summary_flesch": describe(all_summary_flesch),
        "source_flesch_kincaid_grade": describe(source_grade),
        "summary_flesch_kincaid_grade": describe(all_summary_grade),
        "policy_level_flesch_improvement": describe(improvements),
        "policies_with_positive_flesch_improvement": sum(value > 0 for value in improvements),
        "normalised_source_flesch": describe(normalised_source_flesch),
        "normalised_summary_flesch": describe(normalised_summary_flesch),
        "policy_level_normalised_flesch_improvement": describe(normalised_improvements),
        "policies_with_positive_normalised_flesch_improvement": sum(
            value > 0 for value in normalised_improvements
        ),
        "policy_level_mean_compression_ratio": describe(compression),
    }
    (OUTPUT_DIR / "source_summary_readability_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    report = f"""# RQ1 source-versus-summary readability and compression

The same deterministic readability implementation used for the generated outputs was applied to all {len(source_rows)} cleaned source policies. For each policy, its source score was compared with the mean of its nine matched summaries, preventing policies with different lengths from receiving unequal weight in the policy-level comparison.

- Mean source Flesch Reading Ease: {summary['source_flesch']['mean']:.2f}.
- Mean generated-summary Flesch Reading Ease: {summary['summary_flesch']['mean']:.2f}.
- Mean policy-level Flesch improvement: {summary['policy_level_flesch_improvement']['mean']:.2f} points.
- Policies with a positive mean Flesch improvement: {summary['policies_with_positive_flesch_improvement']}/{len(source_rows)}.
- Whitespace-normalised source Flesch mean (layout sensitivity check): {summary['normalised_source_flesch']['mean']:.2f}.
- Whitespace-normalised summary Flesch mean: {summary['normalised_summary_flesch']['mean']:.2f}.
- Mean policy-level normalised Flesch difference: {summary['policy_level_normalised_flesch_improvement']['mean']:.2f} points.
- Policies with a positive normalised Flesch difference: {summary['policies_with_positive_normalised_flesch_improvement']}/{len(source_rows)}.
- Mean source Flesch–Kincaid Grade: {summary['source_flesch_kincaid_grade']['mean']:.2f}.
- Mean generated-summary Flesch–Kincaid Grade: {summary['summary_flesch_kincaid_grade']['mean']:.2f}.
- Mean policy-level word-compression ratio: {summary['policy_level_mean_compression_ratio']['mean']:.3f}.

The frozen metric treats line breaks as sentence boundaries. Because source extraction introduced layout line breaks, the whitespace-normalised calculation is retained as a sensitivity check rather than silently replacing the frozen metric. These formula-based results indicate textual readability and length reduction; they do not establish end-user comprehension. Policy-level matched values are retained in `source_summary_comparison_by_policy.csv`.
"""
    (OUTPUT_DIR / "RQ1_source_summary_report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
