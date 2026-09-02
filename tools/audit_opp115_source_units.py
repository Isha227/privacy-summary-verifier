from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common import ROOT, load_config, read_csv, sha256_text, write_json
from src.v2_statement_verifier import _policy_units


def main() -> None:
    os.environ.setdefault("EXPERIMENT_CONFIG", "config/opp115_extension_v1.0.yaml")
    cfg = load_config()
    settings = cfg["opp115_coverage"]
    base = ROOT / settings["output_dir"]
    by_policy = base / "source_units/by_policy"
    audit_path = base / "audits/source_unit_generation_audit.json"
    metadata = read_csv(ROOT / cfg["paths"]["metadata"])
    policies = sorted({row["policy_id"] for row in metadata})
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    all_ids: list[str] = []

    expected_csvs = {f"{policy_id}_source_units.csv" for policy_id in policies}
    actual_csvs = {path.name for path in by_policy.glob("*_source_units.csv")}
    for name in sorted(expected_csvs - actual_csvs):
        errors.append(f"Missing source-unit file: {name}")
    for name in sorted(actual_csvs - expected_csvs):
        errors.append(f"Unexpected source-unit file: {name}")

    for policy_id in policies:
        csv_path = by_policy / f"{policy_id}_source_units.csv"
        sidecar_path = csv_path.with_suffix(".audit.json")
        rows = read_csv(csv_path)
        if not rows:
            errors.append(f"{policy_id}: no source-unit rows")
            continue
        counts[policy_id] = len(rows)
        policy = (ROOT / cfg["paths"]["clean"] / f"{policy_id}.txt").read_text(encoding="utf-8").strip()
        policy_hash = sha256_text(policy)
        passage_lookup = dict(_policy_units(policy))
        expected_ids = [f"{policy_id}-U{i:03d}" for i in range(1, len(rows) + 1)]
        actual_ids = [row.get("unit_id", "").strip() for row in rows]
        if actual_ids != expected_ids:
            errors.append(f"{policy_id}: unit IDs are not contiguous and ordered")
        normalised_information: list[str] = []
        prompt_hashes: set[str] = set()
        for row_number, row in enumerate(rows, 2):
            unit_id = row.get("unit_id", "").strip() or f"row {row_number}"
            all_ids.append(row.get("unit_id", "").strip())
            for field in (
                "policy_id", "unit_id", "important_information", "importance_reason",
                "source_passage_ids", "exact_source_evidence", "model_id",
                "prompt_sha256", "policy_sha256", "status",
            ):
                if not row.get(field, "").strip():
                    errors.append(f"{unit_id}: blank {field}")
            if row.get("policy_id") != policy_id:
                errors.append(f"{unit_id}: policy_id does not match file")
            if row.get("status") != "success":
                errors.append(f"{unit_id}: status is not success")
            if row.get("error", "").strip():
                errors.append(f"{unit_id}: nonblank error field")
            if row.get("model_id") != settings["model"]:
                errors.append(f"{unit_id}: unexpected model_id")
            if row.get("policy_sha256") != policy_hash:
                errors.append(f"{unit_id}: policy SHA-256 mismatch")
            prompt_hashes.add(row.get("prompt_sha256", "").strip())
            source_ids = [item.strip() for item in row.get("source_passage_ids", "").split(";") if item.strip()]
            if len(source_ids) != len(set(source_ids)):
                errors.append(f"{unit_id}: duplicate source passage ID")
            invalid_ids = [item for item in source_ids if item not in passage_lookup]
            if invalid_ids:
                errors.append(f"{unit_id}: invalid source passage IDs {invalid_ids}")
            elif source_ids:
                expected_evidence = "\n---\n".join(passage_lookup[item] for item in source_ids)
                if row.get("exact_source_evidence", "") != expected_evidence:
                    errors.append(f"{unit_id}: exact source evidence mismatch")
            normalised_information.append(re.sub(r"\s+", " ", row.get("important_information", "")).casefold().strip())
        duplicate_information = [
            text for text, count in Counter(normalised_information).items() if text and count > 1
        ]
        if duplicate_information:
            errors.append(f"{policy_id}: duplicate important-information statements")
        if len(prompt_hashes) != 1 or "" in prompt_hashes:
            errors.append(f"{policy_id}: inconsistent or blank prompt hash")

        if not sidecar_path.is_file():
            errors.append(f"{policy_id}: missing audit sidecar")
        else:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if sidecar.get("policy_id") != policy_id:
                errors.append(f"{policy_id}: audit sidecar policy mismatch")
            if sidecar.get("units") != len(rows):
                errors.append(f"{policy_id}: audit sidecar unit count mismatch")
            if sidecar.get("policy_sha256") != policy_hash:
                errors.append(f"{policy_id}: audit sidecar policy hash mismatch")
            if sidecar.get("prompt_sha256") not in prompt_hashes:
                errors.append(f"{policy_id}: audit sidecar prompt hash mismatch")
            if sidecar.get("taxonomy_visible_to_model") is not False:
                errors.append(f"{policy_id}: taxonomy independence flag is not false")
            if sidecar.get("summaries_visible_to_model") is not False:
                errors.append(f"{policy_id}: summary independence flag is not false")

    duplicate_ids = [item for item, count in Counter(all_ids).items() if item and count > 1]
    if duplicate_ids:
        errors.append(f"Duplicate unit IDs across policies: {duplicate_ids[:10]}")
    if len(policies) != 27:
        errors.append(f"Expected 27 policies, found {len(policies)}")

    result = {
        "status": "pass" if not errors else "fail",
        "policies_expected": 27,
        "policies_complete": len(counts),
        "total_units": sum(counts.values()),
        "units_per_policy": counts,
        "duplicate_unit_ids": duplicate_ids,
        "errors": errors,
        "warnings": warnings,
        "taxonomy_visible_during_identification": False,
        "summaries_visible_during_identification": False,
    }
    write_json(audit_path, result)
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
