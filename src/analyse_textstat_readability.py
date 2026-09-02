"""Independent readability sensitivity analysis using textstat."""

from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

# textstat loads CMUdict during import, so expose the project-local corpus first.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("NLTK_DATA", str(_PROJECT_ROOT / "data" / "nltk_data"))

import nltk
nltk.data.path.insert(0, str(_PROJECT_ROOT / "data" / "nltk_data"))
import textstat

from .common import ROOT


METADATA = ROOT / "data" / "main" / "metadata" / "policies.csv"
LOG = ROOT / "data" / "main" / "logs" / "generation_log.csv"
CLEAN = ROOT / "data" / "main" / "clean"
OUTPUT = ROOT / "outputs" / "textstat_readability_sensitivity"
NLTK_DATA = ROOT / "data" / "nltk_data"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def score(text: str) -> dict[str, float]:
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "flesch_reading_ease": round(float(textstat.flesch_reading_ease(text)), 3),
        "flesch_kincaid_grade": round(float(textstat.flesch_kincaid_grade(text)), 3),
        "smog_index": round(float(textstat.smog_index(text)), 3),
    }


def describe(values: list[float]) -> dict[str, float]:
    return {
        "mean": mean(values),
        "sd": stdev(values) if len(values) > 1 else 0.0,
        "median": median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    nltk.data.path.insert(0, str(NLTK_DATA))
    textstat.set_lang("en_US")
    metadata = {row["policy_id"]: row for row in read_rows(METADATA)}
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in read_rows(LOG):
        if row.get("status") != "success" or row.get("replicate", "1") != "1":
            continue
        key = (row["policy_id"], row["model_family"], row["prompt_strategy"])
        if key not in latest or row.get("timestamp_utc", "") > latest[key].get("timestamp_utc", ""):
            latest[key] = row
    if len(latest) != 270:
        raise RuntimeError(f"Expected 270 frozen main outputs, found {len(latest)}")

    sources: dict[str, dict[str, float]] = {}
    summary_rows: list[dict] = []
    for policy_id in sorted(metadata):
        sources[policy_id] = score((CLEAN / f"{policy_id}.txt").read_text(encoding="utf-8"))
    for (policy_id, model, prompt), row in sorted(latest.items()):
        summary_score = score((ROOT / row["text_path"]).read_text(encoding="utf-8"))
        summary_rows.append({
            "policy_id": policy_id,
            "model_family": model,
            "prompt_strategy": prompt,
            **summary_score,
        })

    by_policy: dict[str, list[dict]] = defaultdict(list)
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in summary_rows:
        by_policy[row["policy_id"]].append(row)
        by_model[row["model_family"]].append(row)

    policy_rows: list[dict] = []
    for policy_id in sorted(metadata):
        rows = by_policy[policy_id]
        source = sources[policy_id]
        summary_flesch = mean(row["flesch_reading_ease"] for row in rows)
        policy_rows.append({
            "policy_id": policy_id,
            "organisation": metadata[policy_id]["organisation"],
            "sector": metadata[policy_id]["sector"],
            "source_flesch_reading_ease": source["flesch_reading_ease"],
            "mean_summary_flesch_reading_ease": round(summary_flesch, 3),
            "flesch_difference": round(summary_flesch - source["flesch_reading_ease"], 3),
            "source_flesch_kincaid_grade": source["flesch_kincaid_grade"],
            "mean_summary_flesch_kincaid_grade": round(
                mean(row["flesch_kincaid_grade"] for row in rows), 3
            ),
            "source_smog_index": source["smog_index"],
            "mean_summary_smog_index": round(mean(row["smog_index"] for row in rows), 3),
            "summaries": len(rows),
        })

    source_flesch = [row["flesch_reading_ease"] for row in sources.values()]
    summary_flesch = [row["flesch_reading_ease"] for row in summary_rows]
    source_grade = [row["flesch_kincaid_grade"] for row in sources.values()]
    summary_grade = [row["flesch_kincaid_grade"] for row in summary_rows]
    source_smog = [row["smog_index"] for row in sources.values()]
    summary_smog = [row["smog_index"] for row in summary_rows]
    differences = [row["flesch_difference"] for row in policy_rows]
    model_summary = {
        model: {
            "summaries": len(rows),
            "flesch_reading_ease": describe([row["flesch_reading_ease"] for row in rows]),
            "flesch_kincaid_grade": describe([row["flesch_kincaid_grade"] for row in rows]),
            "smog_index": describe([row["smog_index"] for row in rows]),
        }
        for model, rows in sorted(by_model.items())
    }
    result = {
        "library": "textstat",
        "library_version": getattr(textstat, "__version__", "0.7.10"),
        "language": "en_US",
        "source_policies": len(sources),
        "generated_summaries": len(summary_rows),
        "source_flesch_reading_ease": describe(source_flesch),
        "summary_flesch_reading_ease": describe(summary_flesch),
        "source_flesch_kincaid_grade": describe(source_grade),
        "summary_flesch_kincaid_grade": describe(summary_grade),
        "source_smog_index": describe(source_smog),
        "summary_smog_index": describe(summary_smog),
        "policy_level_flesch_difference": describe(differences),
        "policies_with_positive_flesch_difference": sum(value > 0 for value in differences),
        "by_model": model_summary,
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_rows(OUTPUT / "textstat_summary_scores.csv", summary_rows)
    write_rows(OUTPUT / "textstat_source_summary_by_policy.csv", policy_rows)
    (OUTPUT / "textstat_readability_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    model_lines = "\n".join(
        f"- {model}: mean Flesch {values['flesch_reading_ease']['mean']:.2f} "
        f"across {values['summaries']} summaries."
        for model, values in model_summary.items()
    )
    report = f"""# textstat readability sensitivity analysis

An independent `textstat` 0.7.10 implementation (US English) was applied to whitespace-normalised versions of all 30 sources and 270 frozen summaries.

- Mean source Flesch Reading Ease: {result['source_flesch_reading_ease']['mean']:.2f}.
- Mean summary Flesch Reading Ease: {result['summary_flesch_reading_ease']['mean']:.2f}.
- Mean matched policy-level difference: {result['policy_level_flesch_difference']['mean']:.2f} points.
- Policies with a positive nine-summary mean difference: {result['policies_with_positive_flesch_difference']}/30.
- Mean source Flesch–Kincaid Grade: {result['source_flesch_kincaid_grade']['mean']:.2f}.
- Mean summary Flesch–Kincaid Grade: {result['summary_flesch_kincaid_grade']['mean']:.2f}.
- Mean source SMOG Grade: {result['source_smog_index']['mean']:.2f}.
- Mean summary SMOG Grade: {result['summary_smog_index']['mean']:.2f}.

## By model

{model_lines}

This is a sensitivity analysis and does not silently replace the frozen custom implementation. Agreement or disagreement between implementations must be reported transparently. Neither implementation measures end-user comprehension.
"""
    (OUTPUT / "TEXTSTAT_READABILITY_REPORT.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
