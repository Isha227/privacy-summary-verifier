from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/opp115/experiment/taxonomy_v3"
PACKAGES = BASE / "contemporary_other_review_packages"
MAPPINGS = BASE / "evaluations/gemini_taxonomy_mappings.csv"
OUT = BASE / "analysis"

CATEGORIES = {
    "First Party Collection/Use", "Third Party Sharing/Collection", "User Choice/Control",
    "User Access, Edit and Deletion", "Data Retention", "Data Security", "Policy Change",
    "Do Not Track", "International and Specific Audiences", "Other",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    reviewers = {
        reviewer: read_csv(PACKAGES / f"contemporary_other_review_{reviewer}_COMPLETED.csv")
        for reviewer in ("A1", "A2", "A3")
    }
    for reviewer, rows in reviewers.items():
        if len(rows) != 7 or {row["review_item_id"] for row in rows} != {f"TREV-{i:03d}" for i in range(1, 8)}:
            raise ValueError(f"Invalid completed package for {reviewer}")
        if any(row["primary_category_decision"] not in CATEGORIES for row in rows):
            raise ValueError(f"Invalid category in {reviewer}")

    by_reviewer = {reviewer: {row["review_item_id"]: row for row in rows} for reviewer, rows in reviewers.items()}
    final_rows = []
    for item_id in (f"TREV-{i:03d}" for i in range(1, 8)):
        source = by_reviewer["A1"][item_id]
        votes = [by_reviewer[r][item_id]["primary_category_decision"] for r in ("A1", "A2", "A3")]
        counts = Counter(votes)
        unanimous = len(counts) == 1
        if unanimous:
            final_category = votes[0]
            resolution = "Unanimous"
            final_reason = "All three researchers independently selected the same OPP category."
        elif item_id == "TREV-007" and counts == Counter({"Other": 2, "Third Party Sharing/Collection": 1}):
            final_category = "Other"
            resolution = "Adjudicated (2-1 decision with definition-based resolution)"
            final_reason = (
                "The statement preserves legal defences or objections but does not assert that third-party "
                "sharing occurs; therefore it does not itself describe a Third Party Sharing/Collection practice."
            )
        else:
            raise ValueError(f"Unresolved disagreement for {item_id}: {dict(counts)}")
        final_rows.append({
            "review_item_id": item_id,
            "policy_id": source["policy_id"],
            "unit_id": source["unit_id"],
            "important_information": source["important_information"],
            "a1_category": votes[0], "a2_category": votes[1], "a3_category": votes[2],
            "final_category": final_category,
            "resolution": resolution,
            "final_reason": final_reason,
        })

    final_path = OUT / "contemporary_other_review_final.csv"
    write_csv(final_path, final_rows, list(final_rows[0]))

    mappings = read_csv(MAPPINGS)
    human = [row.copy() for row in mappings if row["dataset"] == "Contemporary human reference"]
    additions = [row.copy() for row in mappings if row["dataset"] == "Contemporary Gemini validated addition"]
    decisions = {row["unit_id"]: row for row in final_rows}
    changed = []
    for row in human + additions:
        decision = decisions.get(row["unit_id"])
        if decision:
            row["original_gemini_primary_category"] = row["primary_category"]
            row["final_human_reviewed_category"] = decision["final_category"]
            if row["primary_category"] != decision["final_category"]:
                changed.append(row["unit_id"])

    human_counts = Counter(
        decisions.get(row["unit_id"], {}).get("final_category", row["primary_category"])
        for row in human
    )
    addition_counts = Counter(
        decisions.get(row["unit_id"], {}).get("final_category", row["primary_category"])
        for row in additions
    )
    summary = {
        "review_rows": 7,
        "unanimous_rows": 6,
        "adjudicated_rows": 1,
        "exact_unanimous_agreement_percent": round(100 * 6 / 7, 2),
        "changed_from_gemini_other": changed,
        "contemporary_human_reference_units": 165,
        "final_human_reference_other_count": human_counts["Other"],
        "final_human_reference_other_percent": round(100 * human_counts["Other"] / 165, 2),
        "final_human_reference_third_party_count": human_counts["Third Party Sharing/Collection"],
        "validated_additions": 4,
        "final_validated_additions_other_count": addition_counts["Other"],
        "denominator_note": "The four validated Gemini additions remain separate from the 165-unit human reference denominator.",
    }
    (OUT / "contemporary_other_review_final_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
