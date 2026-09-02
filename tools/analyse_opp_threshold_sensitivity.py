from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPP_ROOT = ROOT / "data/opp115/raw/OPP-115_v1_0/OPP-115"
METADATA = ROOT / "data/opp115/frozen/metadata/policies.csv"
UNITS = ROOT / "data/opp115/experiment/coverage_v3/source_units/frozen_source_units.csv"
MAPPINGS = ROOT / "data/opp115/experiment/taxonomy_v3/evaluations/gemini_taxonomy_mappings.csv"
OUT = ROOT / "data/opp115/experiment/taxonomy_v3/analysis/threshold_sensitivity"
THRESHOLDS = ("0.5", "0.75", "1.0")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


def tokens(text: str) -> set[str]:
    return {token for token in normalise(text).split() if len(token) > 1}


def selected_texts(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "selectedText" and isinstance(item, str) and item.strip():
                found.append(item.strip())
            else:
                found.extend(selected_texts(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(selected_texts(item))
    return found


def load_annotations(threshold: str, uid: str) -> tuple[list[dict], int, int]:
    folder = OPP_ROOT / "consolidation" / f"threshold-{threshold}-overlap-similarity"
    matches = sorted(folder.glob(f"{uid}_*.csv"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one {threshold} file for OPP UID {uid}; found {len(matches)}")
    annotations = []
    total = consolidated = 0
    with matches[0].open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.reader(handle):
            if len(raw) < 7:
                continue
            total += 1
            consolidated += int(raw[0].startswith("C"))
            try:
                attributes = json.loads(raw[6])
            except json.JSONDecodeError:
                attributes = {}
            selected = " ".join(dict.fromkeys(selected_texts(attributes))).strip()
            if selected:
                annotations.append({"category": raw[5], "selected": selected})
    return annotations, total, consolidated


def candidate_categories(evidence: str, annotations: list[dict]) -> tuple[set[str], set[str]]:
    evidence_norm = normalise(evidence)
    evidence_tokens = tokens(evidence)
    all_categories: set[str] = set()
    strong_categories: set[str] = set()
    for annotation in annotations:
        selected = annotation["selected"]
        selected_norm = normalise(selected)
        selected_tokens = tokens(selected)
        if not selected_tokens or not evidence_tokens:
            continue
        intersection = len(evidence_tokens & selected_tokens)
        containment = intersection / min(len(evidence_tokens), len(selected_tokens))
        substring = selected_norm in evidence_norm or evidence_norm in selected_norm
        if substring or (intersection >= 4 and containment >= 0.60):
            all_categories.add(annotation["category"])
            if substring or containment >= 0.80:
                strong_categories.add(annotation["category"])
    return all_categories, strong_categories


def percent(n: int, d: int) -> float:
    return round(100 * n / d, 2) if d else 0.0


def main() -> None:
    metadata = {row["policy_id"]: row for row in read_csv(METADATA)}
    units = read_csv(UNITS)
    primary = {
        row["unit_id"]: row["primary_category"]
        for row in read_csv(MAPPINGS) if row["dataset"] == "OPP historical"
    }
    if len(units) != 1008 or len(primary) != 1008:
        raise ValueError("Expected 1,008 OPP units and mappings")

    unit_rows: list[dict] = []
    summary_rows: list[dict] = []
    category_rows: list[dict] = []
    compatibility_by_threshold: dict[str, dict[str, str]] = {}

    for threshold in THRESHOLDS:
        annotations_by_policy = {}
        annotation_rows = consolidated_rows = 0
        for policy_id, row in metadata.items():
            annotations, total, consolidated = load_annotations(threshold, row["opp_policy_uid"])
            annotations_by_policy[policy_id] = annotations
            annotation_rows += total
            consolidated_rows += consolidated

        mapped = compatible = strong_mapped = strong_compatible = 0
        category_totals = Counter()
        category_compatible = Counter()
        threshold_compatibility = {}
        for unit in units:
            categories, strong_categories = candidate_categories(
                unit["exact_source_evidence"], annotations_by_policy[unit["policy_id"]]
            )
            label = primary[unit["unit_id"]]
            result = "Yes" if categories and label in categories else ("No" if categories else "Not testable")
            strong_result = (
                "Yes" if strong_categories and label in strong_categories
                else ("No" if strong_categories else "Not testable")
            )
            mapped += int(bool(categories))
            compatible += int(result == "Yes")
            strong_mapped += int(bool(strong_categories))
            strong_compatible += int(strong_result == "Yes")
            category_totals[label] += int(bool(categories))
            category_compatible[label] += int(result == "Yes")
            threshold_compatibility[unit["unit_id"]] = result
            unit_rows.append({
                "threshold": threshold,
                "policy_id": unit["policy_id"],
                "unit_id": unit["unit_id"],
                "gemini_primary_category": label,
                "overlapping_opp_categories": "; ".join(sorted(categories)),
                "compatibility": result,
                "strong_overlapping_opp_categories": "; ".join(sorted(strong_categories)),
                "strong_compatibility": strong_result,
            })
        compatibility_by_threshold[threshold] = threshold_compatibility
        summary_rows.append({
            "threshold": threshold,
            "annotation_rows": annotation_rows,
            "consolidated_rows": consolidated_rows,
            "singlet_rows": annotation_rows - consolidated_rows,
            "units": len(units),
            "testable_units": mapped,
            "compatible_units": compatible,
            "compatibility_percent": f"{percent(compatible, mapped):.2f}",
            "untestable_units": len(units) - mapped,
            "strong_testable_units": strong_mapped,
            "strong_compatible_units": strong_compatible,
            "strong_compatibility_percent": f"{percent(strong_compatible, strong_mapped):.2f}",
        })
        for category in sorted(category_totals):
            category_rows.append({
                "threshold": threshold,
                "category": category,
                "testable_units": category_totals[category],
                "compatible_units": category_compatible[category],
                "compatibility_percent": f"{percent(category_compatible[category], category_totals[category]):.2f}",
            })

    transition_rows = []
    for unit in units:
        results = {threshold: compatibility_by_threshold[threshold][unit["unit_id"]] for threshold in THRESHOLDS}
        transition_rows.append({
            "policy_id": unit["policy_id"],
            "unit_id": unit["unit_id"],
            "gemini_primary_category": primary[unit["unit_id"]],
            "at_0_5": results["0.5"],
            "at_0_75": results["0.75"],
            "at_1_0": results["1.0"],
            "same_result_all_thresholds": "Yes" if len(set(results.values())) == 1 else "No",
        })

    write_csv(OUT / "threshold_summary.csv", summary_rows, list(summary_rows[0]))
    write_csv(OUT / "unit_level_threshold_results.csv", unit_rows, list(unit_rows[0]))
    write_csv(OUT / "category_level_threshold_results.csv", category_rows, list(category_rows[0]))
    write_csv(OUT / "unit_result_stability.csv", transition_rows, list(transition_rows[0]))

    rates = [float(row["compatibility_percent"]) for row in summary_rows]
    stability_count = sum(row["same_result_all_thresholds"] == "Yes" for row in transition_rows)
    result = {
        "thresholds": summary_rows,
        "compatibility_rate_range_pp": round(max(rates) - min(rates), 2),
        "units_with_same_status_at_all_thresholds": stability_count,
        "unit_status_stability_percent": percent(stability_count, len(transition_rows)),
        "robust_conclusion": max(rates) - min(rates) <= 5.0,
        "interpretation": (
            "The thresholds alter consolidation strictness, not annotator expertise or label quality. "
            "Robustness is assessed by whether the overall compatibility conclusion remains similar."
        ),
    }
    (OUT / "threshold_sensitivity_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
