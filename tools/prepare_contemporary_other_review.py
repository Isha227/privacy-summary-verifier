from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/opp115/experiment/taxonomy_v3/analysis/contemporary_other_review.csv"
OUT = ROOT / "data/opp115/experiment/taxonomy_v3/contemporary_other_review_packages"

FIELDS = [
    "review_item_id", "policy_id", "unit_id", "important_information",
    "material_qualifiers", "exact_source_evidence", "primary_category_decision",
    "reason", "confidence",
]

INSTRUCTIONS = """# Contemporary OPP taxonomy review

## Purpose

Independently decide whether each of the seven important source units belongs in one of the nine specific OPP categories or in the official catch-all category `Other`.

This is not a new source-unit identification task. Do not add, delete, merge or split units. Do not evaluate summaries. Use only the supplied proposition, qualifiers, evidence and the official category definitions below.

## Required fields

For every row, complete:

- `primary_category_decision`: exactly one official category;
- `reason`: a concise explanation tied to the unit's principal privacy practice;
- `confidence`: High, Medium or Low.

Work independently and do not view another researcher's decisions before submitting your file.

## Official OPP categories

- **First Party Collection/Use:** data collection or use by the organisation owning the service.
- **Third Party Sharing/Collection:** data sharing with, or collection by, another organisation.
- **User Choice/Control:** general choices and control options available to users.
- **User Access, Edit and Deletion:** allowing users to access, edit or delete held data.
- **Data Retention:** retention periods or criteria for collected information.
- **Data Security:** how information is secured and protected.
- **Policy Change:** whether and how users are informed of policy changes and related choices.
- **Do Not Track:** whether and how Do Not Track signals are honoured.
- **International and Specific Audiences:** special provisions for particular audiences, such as children, international users or another specifically treated group.
- **Other:** the principal proposition is not adequately described by any specific category above.

Choose the category describing the principal privacy practice, not merely a word in the evidence. Do not force a unit into a specific category when `Other` is genuinely the best fit.
"""


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    if len(source_rows) != 7:
        raise ValueError(f"Expected seven review units, found {len(source_rows)}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "README.md").write_text(INSTRUCTIONS, encoding="utf-8")
    for reviewer in ("A1", "A2", "A3"):
        rows = []
        for index, row in enumerate(source_rows, 1):
            rows.append({
                "review_item_id": f"TREV-{index:03d}",
                "policy_id": row["policy_id"],
                "unit_id": row["unit_id"],
                "important_information": row["important_information"],
                "material_qualifiers": row["material_qualifiers"],
                "exact_source_evidence": row["exact_source_evidence"],
                "primary_category_decision": "",
                "reason": "",
                "confidence": "",
            })
        path = OUT / f"contemporary_other_review_{reviewer}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Prepared 3 independent packages with {len(source_rows)} rows each: {OUT}")


if __name__ == "__main__":
    main()
