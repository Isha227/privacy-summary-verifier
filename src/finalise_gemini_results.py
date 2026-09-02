from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .common import ROOT, load_config, read_csv
from .faithfulness import GEMINI_FIELDS, _approved_claims, _write_csv


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalise() -> tuple[int, int, Path]:
    cfg = load_config()
    model = cfg["faithfulness"]["gemini_model"]
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    result_dir = ROOT / cfg["faithfulness"]["results_dir"]
    raw_path = result_dir / f"gemini_claim_scores_batched__{safe_model}.csv"
    clean_path = result_dir / f"gemini_claim_scores_final__{safe_model}.csv"
    audit_path = result_dir / f"gemini_duplicate_audit__{safe_model}.csv"

    expected_rows = _approved_claims()
    expected = {(row["blind_id"], row["claim_id"]) for row in expected_rows}
    occurrences: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in read_csv(raw_path):
        if row.get("status") == "success":
            occurrences[(row["blind_id"], row["claim_id"])].append(row)

    observed = set(occurrences)
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        raise RuntimeError(
            f"Gemini coverage mismatch: missing={len(missing)}, unexpected={len(unexpected)}"
        )

    # The runner's intended rule is first valid success wins; retain file order.
    selected = [occurrences[key][0] for key in sorted(expected)]
    _write_csv(clean_path, GEMINI_FIELDS, selected)

    audit_rows = []
    for key in sorted(expected):
        rows = occurrences[key]
        if len(rows) <= 1:
            continue
        labels = list(dict.fromkeys(row["label"] for row in rows))
        audit_rows.append({
            "blind_id": key[0],
            "claim_id": key[1],
            "occurrences": len(rows),
            "distinct_labels": " | ".join(labels),
            "label_conflict": str(len(labels) > 1).lower(),
            "selected_rule": "first_valid_success",
            "selected_label": rows[0]["label"],
            "selected_timestamp_utc": rows[0].get("timestamp_utc", ""),
            "selected_response_id": rows[0].get("response_id", ""),
        })
    if audit_rows:
        with audit_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=audit_rows[0].keys())
            writer.writeheader()
            writer.writerows(audit_rows)

    freeze_path = result_dir / f"gemini_results_freeze__{safe_model}.json"
    freeze_path.write_text(json.dumps({
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "first valid successful judgement per blind_id and claim_id",
        "expected_unique_claims": len(expected),
        "final_unique_claims": len(selected),
        "duplicate_claim_ids": len(audit_rows),
        "raw_file": str(raw_path.relative_to(ROOT)),
        "raw_sha256": _sha256(raw_path),
        "final_file": str(clean_path.relative_to(ROOT)),
        "final_sha256": _sha256(clean_path),
        "duplicate_audit_file": str(audit_path.relative_to(ROOT)),
        "duplicate_audit_sha256": _sha256(audit_path),
    }, indent=2) + "\n", encoding="utf-8")
    return len(selected), len(audit_rows), clean_path


if __name__ == "__main__":
    count, duplicates, path = finalise()
    print(f"Finalised {count} unique Gemini claims; audited {duplicates} duplicated claim IDs: {path}")
