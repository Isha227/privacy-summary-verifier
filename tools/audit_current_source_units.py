from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["EXPERIMENT_CONFIG"] = "config/v2_prompt_intervention_v1.2.yaml"

from src.common import ROOT, load_config, read_csv, sha256_text  # noqa: E402
from src.v2_statement_verifier import _policy_units  # noqa: E402


POLICIES = ["PILOT01", "PILOT02", "PILOT03"]
BASE = ROOT / "data/v2_prompt_intervention_v1_2/source_unit_method_validation/gemini_v2/by_policy"
cfg = load_config()
summary = {"policies": {}, "total_units": 0, "errors": []}

for policy_id in POLICIES:
    csv_path = BASE / f"{policy_id}_gemini_source_units_v2.csv"
    audit_path = csv_path.with_suffix(".audit.json")
    rows = read_csv(csv_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    policy = (ROOT / cfg["paths"]["clean"] / f"{policy_id}.txt").read_text(encoding="utf-8").strip()
    lookup = dict(_policy_units(policy))
    expected_ids = [f"GV2-{policy_id.replace('PILOT', 'P')}-U{i:03d}" for i in range(1, len(rows) + 1)]
    policy_errors = []
    if not rows:
        policy_errors.append("no rows")
    if [row.get("candidate_unit_id") for row in rows] != expected_ids:
        policy_errors.append("non-contiguous candidate IDs")
    if len({row.get("candidate_unit_id") for row in rows}) != len(rows):
        policy_errors.append("duplicate candidate IDs")
    for row in rows:
        evidence_ids = [item for item in row.get("source_passage_ids", "").split(";") if item]
        expected_evidence = "\n---\n".join(lookup[item] for item in evidence_ids if item in lookup)
        if not evidence_ids or any(item not in lookup for item in evidence_ids):
            policy_errors.append(f"{row.get('candidate_unit_id')}: invalid evidence ID")
        elif row.get("exact_source_evidence") != expected_evidence:
            policy_errors.append(f"{row.get('candidate_unit_id')}: evidence text mismatch")
        if not row.get("important_information", "").strip():
            policy_errors.append(f"{row.get('candidate_unit_id')}: blank information")
        if not row.get("importance_reason", "").strip():
            policy_errors.append(f"{row.get('candidate_unit_id')}: blank importance reason")
        if row.get("status") != "success":
            policy_errors.append(f"{row.get('candidate_unit_id')}: unsuccessful status")
    if audit.get("policy_sha256") != sha256_text(policy):
        policy_errors.append("policy hash mismatch")
    for field in ("summaries_visible", "human_units_visible", "taxonomy_visible"):
        if audit.get(field) is not False:
            policy_errors.append(f"audit does not confirm {field}=false")
    if audit.get("source_evidence_retrieved_by_program") is not True:
        policy_errors.append("audit does not confirm programmatic evidence retrieval")
    summary["policies"][policy_id] = {"units": len(rows), "errors": policy_errors}
    summary["total_units"] += len(rows)
    summary["errors"].extend(f"{policy_id}: {error}" for error in policy_errors)

summary["valid"] = not summary["errors"] and summary["total_units"] > 0
destination = ROOT / "data/v2_prompt_intervention_v1_2/source_unit_method_validation/audits/gemini_v2_source_units_audit.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
