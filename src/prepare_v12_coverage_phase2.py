from __future__ import annotations

import csv

from .common import ROOT, read_csv


BASE = ROOT / "data/v2_prompt_intervention_v1_2"
ADJ = BASE / "human_evaluation/adjudication"


def main() -> None:
    frozen_path = ADJ / "frozen_source_units_FINAL.csv"
    units = read_csv(frozen_path)
    if not units:
        raise RuntimeError(
            "Coverage Phase 2 cannot be generated until frozen_source_units_FINAL.csv "
            "has been completed through human adjudication."
        )
    required = {"policy_id", "final_unit_id", "important_information", "exact_source_quote", "material_qualifiers"}
    missing = required - set(units[0])
    if missing: raise ValueError(f"Frozen source-unit file lacks columns: {sorted(missing)}")
    ids = [row["final_unit_id"] for row in units]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("Final unit IDs must be populated and unique")
    key = read_csv(BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv")
    rows = []
    for unit in units:
        summaries = sorted((row for row in key if row["policy_id"] == unit["policy_id"]), key=lambda row: row["blind_id"])
        if len(summaries) != 18:
            raise ValueError(f"Expected 18 summaries for {unit['policy_id']}; found {len(summaries)}")
        for summary in summaries:
            summary_path = BASE / "anonymised" / f"{summary['blind_id']}.txt"
            if not summary_path.exists():
                raise FileNotFoundError(f"Missing blinded summary: {summary_path}")
            rows.append({
                "comparison_id": f"{summary['blind_id']}--{unit['final_unit_id']}",
                "policy_id": unit["policy_id"], "blind_id": summary["blind_id"],
                "final_unit_id": unit["final_unit_id"],
                "important_information": unit["important_information"],
                "exact_source_quote": unit["exact_source_quote"],
                "material_qualifiers": unit["material_qualifiers"],
                "summary_text": summary_path.read_text(encoding="utf-8").strip(),
                "coverage_label": "", "summary_evidence": "", "reason": "", "confidence": "",
            })
    output_dir = BASE / "human_evaluation/coverage_phase2"
    output_dir.mkdir(parents=True, exist_ok=True)
    for evaluator in ("A1", "A2", "A3"):
        path = output_dir / f"human_v12_{evaluator}_COVERAGE_PHASE2.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(rows)
    print(f"Prepared {len(rows)} identical coverage comparisons for each researcher")


if __name__ == "__main__":
    main()
