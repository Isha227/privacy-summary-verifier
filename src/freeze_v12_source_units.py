from __future__ import annotations

import csv
from collections import defaultdict

from .common import ROOT, read_csv


BASE = ROOT / "data/v2_prompt_intervention_v1_2"
ADJ = BASE / "human_evaluation/adjudication"


def _canonical_row(rows: list[dict[str, str]]) -> dict[str, str]:
    marked = [row for row in rows if "canonical" in row.get("adjudication_notes", "").casefold()]
    if len(rows) > 1 and len(marked) != 1:
        raise ValueError(
            f"Merged unit {rows[0]['final_unit_id']} must identify exactly one canonical proposal; "
            f"found {len(marked)}"
        )
    return marked[0] if marked else rows[0]


def main() -> None:
    source_path = ADJ / "source_unit_proposals_ADJUDICATED.csv"
    proposals = read_csv(source_path)
    if not proposals:
        raise RuntimeError(f"No adjudicated source-unit proposals found at {source_path}")

    retained = [row for row in proposals if row.get("retain_in_frozen_set") == "Yes"]
    rejected = [row for row in proposals if row.get("retain_in_frozen_set") == "No"]
    undecided = [row for row in proposals if row.get("retain_in_frozen_set") not in {"Yes", "No"}]
    if undecided:
        raise ValueError(f"{len(undecided)} source-unit proposals lack a valid retain decision")

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in retained:
        final_id = row.get("final_unit_id", "").strip()
        if not final_id:
            raise ValueError(f"Retained proposal {row.get('proposed_unit_id')} lacks final_unit_id")
        grouped[final_id].append(row)

    frozen: list[dict[str, str | int]] = []
    for final_id in sorted(grouped):
        rows = grouped[final_id]
        policies = {row["policy_id"] for row in rows}
        if len(policies) != 1:
            raise ValueError(f"Final unit {final_id} crosses policies: {sorted(policies)}")
        canonical = _canonical_row(rows)
        frozen.append(
            {
                "policy_id": canonical["policy_id"],
                "final_unit_id": final_id,
                "important_information": canonical["important_information_in_plain_language"],
                "exact_source_quote": canonical["exact_source_quote"],
                "material_qualifiers": canonical.get("material_qualifiers", ""),
                "why_important_to_user": canonical.get("why_important_to_user", ""),
                "canonical_proposal_id": canonical["proposed_unit_id"],
                "merged_proposal_count": len(rows),
                "adjudication_notes": canonical.get("adjudication_notes", ""),
            }
        )

    if len(frozen) != 165:
        raise ValueError(f"Expected 165 frozen units after adjudication; found {len(frozen)}")
    output_path = ADJ / "frozen_source_units_FINAL.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(frozen[0]))
        writer.writeheader()
        writer.writerows(frozen)
    print(
        f"Frozen {len(frozen)} units from {len(retained)} retained proposals; "
        f"{len(rejected)} proposals rejected: {output_path}"
    )


if __name__ == "__main__":
    main()
