from __future__ import annotations

from collections import Counter

from .common import ROOT, load_config, read_csv


def main() -> None:
    cfg = load_config()
    root = ROOT / cfg["v2_evaluation"]["root"] / "evaluations"
    statement_files = sorted((root / "gemini_statement_verification").glob("*/S*_statement_verification_v1.3.csv"))
    coverage_files = sorted((root / "gemini_preliminary_coverage").glob("*/S*_gemini_coverage_v1.0.csv"))
    unit_files = sorted((root / "gemini_source_units").glob("*/PILOT*_gemini_source_units_v1.0.csv"))
    statements = [row for path in statement_files for row in read_csv(path)]
    coverage = [row for path in coverage_files for row in read_csv(path)]
    units = [row for path in unit_files for row in read_csv(path)]
    assert len(statement_files) == 54 and len(coverage_files) == 54 and len(unit_files) == 3
    assert len(statements) == 1393
    assert len({row["statement_id"] for row in statements}) == 1393
    invalid_statements = [row for row in statements if row["status"] != "success" or row["evidence_verified"] != "true"]
    assert len({row["blind_id"] for row in statements}) == 54
    pairs = {(row["blind_id"], row["proposed_unit_id"]) for row in coverage}
    assert len(coverage) == len(pairs) == 936
    invalid_coverage = [row for row in coverage if row["status"] != "success" or row["evidence_verified"] != "true"]
    assert len({row["blind_id"] for row in coverage}) == 54
    valid_units = [row for row in units if row["status"] == "success"]
    print(f"Gemini faithfulness: files={len(statement_files)} rows={len(statements)} summaries=54")
    print(f"Gemini preliminary coverage: files={len(coverage_files)} comparisons={len(coverage)} summaries=54")
    print(f"Gemini source units: proposed={len(units)} evidence_valid={len(valid_units)}")
    print(f"Evidence-invalid statement rows: {len(invalid_statements)}")
    print(f"Evidence-invalid coverage rows: {len(invalid_coverage)}")
    if invalid_statements:
        print("Invalid statement IDs:", [row["statement_id"] for row in invalid_statements])
    if invalid_coverage:
        print("Invalid coverage pairs:", [(row["blind_id"], row["proposed_unit_id"]) for row in invalid_coverage])
    print("Valid units by policy:", dict(Counter(row["policy_id"] for row in valid_units)))
    print("Faithfulness labels:", dict(Counter(row["label"] for row in statements)))
    print("Failure types:", dict(Counter(row["failure_type"] for row in statements)))
    print("Coverage labels:", dict(Counter(row["coverage_label"] for row in coverage)))
    assert not invalid_statements and not invalid_coverage


if __name__ == "__main__":
    main()
