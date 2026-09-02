from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/opp115/experiment/taxonomy_v3"
MAPPINGS = BASE / "evaluations/gemini_taxonomy_mappings.csv"
CANDIDATES = ROOT / "data/opp115/experiment/coverage_v3/taxonomy/opp115_unit_taxonomy_candidates.csv"
OUT = BASE / "analysis"

CATEGORIES = [
    "First Party Collection/Use",
    "Third Party Sharing/Collection",
    "User Choice/Control",
    "User Access, Edit and Deletion",
    "Data Retention",
    "Data Security",
    "Policy Change",
    "Do Not Track",
    "International and Specific Audiences",
    "Other",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 2) if d else 0.0


def main() -> None:
    mappings = read_csv(MAPPINGS)
    if len(mappings) != 1177 or len({r["mapping_id"] for r in mappings}) != 1177:
        raise ValueError("Expected 1,177 unique successful mappings")

    candidates_by_unit: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(CANDIDATES):
        if row.get("opp_category"):
            candidates_by_unit[row["unit_id"]].append(row)

    historical = [r for r in mappings if r["dataset"] == "OPP historical"]
    human = [r for r in mappings if r["dataset"] == "Contemporary human reference"]
    additions = [r for r in mappings if r["dataset"] == "Contemporary Gemini validated addition"]
    if (len(historical), len(human), len(additions)) != (1008, 165, 4):
        raise ValueError("Unexpected dataset split")

    validation_rows = []
    mapped = compatible = 0
    strong_mapped = strong_compatible = 0
    for row in historical:
        candidates = candidates_by_unit.get(row["unit_id"], [])
        categories = sorted({c["opp_category"] for c in candidates})
        strong = [
            c for c in candidates
            if c["overlap_method"] == "normalised_substring"
            or float(c.get("token_containment") or 0) >= 0.80
        ]
        strong_categories = sorted({c["opp_category"] for c in strong})
        is_compatible = bool(categories) and row["primary_category"] in categories
        strong_is_compatible = bool(strong_categories) and row["primary_category"] in strong_categories
        mapped += int(bool(categories))
        compatible += int(is_compatible)
        strong_mapped += int(bool(strong_categories))
        strong_compatible += int(strong_is_compatible)
        validation_rows.append({
            "policy_id": row["policy_id"],
            "unit_id": row["unit_id"],
            "important_information": row["important_information"],
            "gemini_primary_category": row["primary_category"],
            "overlapping_opp_categories": "; ".join(categories),
            "compatible_with_overlapping_opp_annotation": "Yes" if is_compatible else ("No" if categories else "Not testable"),
            "strong_overlapping_opp_categories": "; ".join(strong_categories),
            "compatible_with_strong_overlap": "Yes" if strong_is_compatible else ("No" if strong_categories else "Not testable"),
            "gemini_confidence": row["confidence"],
            "gemini_explanation": row["explanation"],
        })

    distribution_rows = []
    datasets = [
        ("OPP historical", historical),
        ("Contemporary human reference", human),
        ("Contemporary Gemini validated additions", additions),
    ]
    for dataset, rows in datasets:
        counts = Counter(r["primary_category"] for r in rows)
        policy_sets: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            policy_sets[r["policy_id"]].add(r["primary_category"])
        policies = len(policy_sets)
        for category in CATEGORIES:
            policy_count = sum(category in found for found in policy_sets.values())
            distribution_rows.append({
                "dataset": dataset,
                "category": category,
                "unit_count": counts[category],
                "unit_percent": f"{pct(counts[category], len(rows)):.2f}",
                "policies_with_category": policy_count,
                "policy_count": policies,
                "policy_prevalence_percent": f"{pct(policy_count, policies):.2f}",
            })

    historical_pct = {r["category"]: float(r["unit_percent"]) for r in distribution_rows if r["dataset"] == "OPP historical"}
    contemporary_pct = {r["category"]: float(r["unit_percent"]) for r in distribution_rows if r["dataset"] == "Contemporary human reference"}
    compatible_ids = {
        r["unit_id"] for r in validation_rows
        if r["compatible_with_overlapping_opp_annotation"] == "Yes"
    }
    compatible_historical = [r for r in historical if r["unit_id"] in compatible_ids]
    compatible_counts = Counter(r["primary_category"] for r in compatible_historical)
    compatible_pct = {
        category: pct(compatible_counts[category], len(compatible_historical))
        for category in CATEGORIES
    }
    difference_rows = [{
        "category": category,
        "opp_historical_unit_percent": f"{historical_pct[category]:.2f}",
        "opp_compatible_subset_percent": f"{compatible_pct[category]:.2f}",
        "contemporary_human_unit_percent": f"{contemporary_pct[category]:.2f}",
        "contemporary_minus_historical_pp": f"{contemporary_pct[category] - historical_pct[category]:.2f}",
        "contemporary_minus_compatible_subset_pp": f"{contemporary_pct[category] - compatible_pct[category]:.2f}",
        "difference_direction_stable": (
            "Yes" if (contemporary_pct[category] - historical_pct[category])
            * (contemporary_pct[category] - compatible_pct[category]) >= 0 else "No"
        ),
    } for category in CATEGORIES]

    other_review = [
        {
            "dataset": r["dataset"], "policy_id": r["policy_id"], "unit_id": r["unit_id"],
            "important_information": r["important_information"],
            "material_qualifiers": r["material_qualifiers"],
            "exact_source_evidence": r["exact_source_evidence"],
            "gemini_explanation": r["explanation"], "confidence": r["confidence"],
            "researcher_review": "", "review_notes": "",
        }
        for r in human + additions if r["primary_category"] == "Other"
    ]

    addition_rows = [{
        "policy_id": r["policy_id"], "unit_id": r["unit_id"],
        "important_information": r["important_information"],
        "primary_category": r["primary_category"],
        "secondary_categories": r["secondary_categories"],
        "explanation": r["explanation"], "confidence": r["confidence"],
    } for r in additions]

    write_csv(OUT / "historical_annotation_validation.csv", validation_rows, list(validation_rows[0]))
    write_csv(OUT / "category_distribution.csv", distribution_rows, list(distribution_rows[0]))
    write_csv(OUT / "historical_contemporary_difference.csv", difference_rows, list(difference_rows[0]))
    write_csv(OUT / "contemporary_other_review.csv", other_review, list(other_review[0]) if other_review else [
        "dataset", "policy_id", "unit_id", "important_information", "material_qualifiers",
        "exact_source_evidence", "gemini_explanation", "confidence", "researcher_review", "review_notes",
    ])
    write_csv(OUT / "validated_gemini_additions_categories.csv", addition_rows, list(addition_rows[0]))

    mismatches = [r for r in validation_rows if r["compatible_with_overlapping_opp_annotation"] == "No"]
    summary = {
        "mapping_integrity": {
            "total": len(mappings), "historical": len(historical),
            "contemporary_human_reference": len(human),
            "contemporary_validated_gemini_additions": len(additions),
        },
        "historical_validation": {
            "units_with_any_overlap_reference": mapped,
            "units_without_overlap_reference": len(historical) - mapped,
            "primary_category_compatible": compatible,
            "compatibility_percent": pct(compatible, mapped),
            "units_with_strong_overlap_reference": strong_mapped,
            "strong_primary_category_compatible": strong_compatible,
            "strong_compatibility_percent": pct(strong_compatible, strong_mapped),
            "noncompatible_units": len(mismatches),
            "high_confidence_noncompatible_units": sum(r["gemini_confidence"] == "High" for r in mismatches),
            "compatible_subset_units_used_for_sensitivity_analysis": len(compatible_historical),
            "interpretation": (
                "Compatibility means Gemini's primary category appears among official OPP annotation "
                "categories whose annotated text overlaps the same frozen source-unit evidence. "
                "It is a historical consistency check, not independent human validation of every mapping."
            ),
        },
        "contemporary": {
            "human_reference_other_units_requiring_qualitative_review": sum(r["dataset"] == "Contemporary human reference" for r in other_review),
            "validated_addition_other_units_requiring_qualitative_review": sum(r["dataset"] == "Contemporary Gemini validated addition" for r in other_review),
            "categories_present_in_human_reference": sorted({r["primary_category"] for r in human}),
            "categories_absent_from_human_reference": [c for c in CATEGORIES if c not in {r["primary_category"] for r in human}],
        },
        "sensitivity_analysis": {
            "category_difference_directions_stable": sum(r["difference_direction_stable"] == "Yes" for r in difference_rows),
            "categories_compared": len(CATEGORIES),
            "interpretation": "Direction is compared between the full historical mapping and the 883-unit historically compatible subset.",
        },
        "cautions": [
            "Unit proportions are descriptive because source-unit granularity differs by policy and dataset.",
            "The contemporary corpus contains only three policies, so differences are not population-wide trends.",
            "An Other mapping is a review flag, not automatic evidence that the OPP taxonomy is outdated.",
            "The four validated Gemini additions remain separate from the 165-unit human reference denominator.",
        ],
    }
    (OUT / "taxonomy_v3_analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
