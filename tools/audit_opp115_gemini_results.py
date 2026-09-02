from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/opp115/experiment"
CLAIMS = BASE / "faithfulness/prepared/claim_candidates.csv"
KEY = BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv"
RESULTS = BASE / "evaluations/faithfulness/gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"
OUTPUT = BASE / "audits/gemini_source_alignment_progress.json"


def read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


claim_rows = read(CLAIMS)
expected = {(row["blind_id"], row["claim_id"]) for row in claim_rows if row.get("include", "yes") == "yes"}
mapping = {row["blind_id"]: row["policy_id"] for row in read(KEY)}
rows = [row for row in read(RESULTS) if row.get("status") == "success"]
keys = [(row["blind_id"], row["claim_id"]) for row in rows]
valid_labels = {"Supported", "Partially supported", "Unsupported", "Contradicted"}
source_cache: dict[str, str] = {}


def source_for(blind_id: str) -> str:
    if blind_id not in source_cache:
        source_cache[blind_id] = (ROOT / "data/opp115/frozen/clean" / f"{mapping[blind_id]}.txt").read_text(encoding="utf-8")
    return source_cache[blind_id]


def evidence_exact(row: dict[str, str]) -> bool:
    evidence = row.get("evidence_quote", "").strip()
    if not evidence:
        return row.get("label") == "Unsupported"
    passages = [item.strip() for item in evidence.split("\n---\n") if item.strip()]
    source = source_for(row["blind_id"])
    return bool(passages) and all(passage in source for passage in passages)


audit = {
    "expected_claims": len(expected),
    "successful_rows": len(rows),
    "unique_successful_claims": len(set(keys)),
    "remaining_claims": len(expected - set(keys)),
    "duplicate_success_rows": len(rows) - len(set(keys)),
    "unexpected_claims": len(set(keys) - expected),
    "invalid_labels": sum(row.get("label") not in valid_labels for row in rows),
    "blank_explanations": sum(not row.get("explanation", "").strip() for row in rows),
    "invalid_evidence_rows": sum(not evidence_exact(row) for row in rows),
    "label_distribution": dict(Counter(row["label"] for row in rows)),
    "summaries_represented": len({row["blind_id"] for row in rows}),
}
audit["valid_so_far"] = (
    audit["duplicate_success_rows"] == 0
    and audit["unexpected_claims"] == 0
    and audit["invalid_labels"] == 0
    and audit["blank_explanations"] == 0
    and audit["invalid_evidence_rows"] == 0
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
print(json.dumps(audit, indent=2))

