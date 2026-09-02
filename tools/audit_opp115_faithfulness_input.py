from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/opp115/experiment"
CLAIMS = BASE / "faithfulness/prepared/claim_candidates.csv"
KEY = BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv"
OUTPUT = BASE / "audits/faithfulness_input_audit.json"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


claims = read(CLAIMS)
key = read(KEY)
claim_keys = [(row["blind_id"], row["claim_id"]) for row in claims]
by_blind: dict[str, list[dict[str, str]]] = defaultdict(list)
for row in claims:
    by_blind[row["blind_id"]].append(row)

non_contiguous = []
for blind_id, rows in sorted(by_blind.items()):
    expected = [f"{blind_id}-C{i:03d}" for i in range(1, len(rows) + 1)]
    observed = [row["claim_id"] for row in rows]
    if observed != expected:
        non_contiguous.append(blind_id)

counts = [len(rows) for rows in by_blind.values()]
key_blind_ids = [row["blind_id"] for row in key]
key_run_ids = [row["run_id"] for row in key]

audit = {
    "claims": len(claims),
    "unique_claim_keys": len(set(claim_keys)),
    "blinded_summaries_in_claims": len(by_blind),
    "blinding_key_rows": len(key),
    "unique_blind_ids_in_key": len(set(key_blind_ids)),
    "unique_run_ids_in_key": len(set(key_run_ids)),
    "claim_count_per_summary": {
        "minimum": min(counts),
        "maximum": max(counts),
        "mean": round(sum(counts) / len(counts), 2),
    },
    "claims_per_model": dict(Counter(next(item["model_family"] for item in key if item["blind_id"] == blind) for blind, rows in by_blind.items() for _ in rows)),
    "summaries_per_policy": dict(Counter(row["policy_id"] for row in key)),
    "summaries_per_model": dict(Counter(row["model_family"] for row in key)),
    "summaries_per_prompt_strategy": dict(Counter(row["prompt_strategy"] for row in key)),
    "blank_claim_texts": sum(not row["claim_text"].strip() for row in claims),
    "excluded_claims": sum(row.get("include", "yes").strip().lower() != "yes" for row in claims),
    "non_contiguous_claim_id_summaries": non_contiguous,
    "claims_sha256": hashlib.sha256(CLAIMS.read_bytes()).hexdigest(),
    "blinding_key_sha256": hashlib.sha256(KEY.read_bytes()).hexdigest(),
}

audit["valid"] = (
    audit["claims"] == audit["unique_claim_keys"]
    and audit["blinded_summaries_in_claims"] == 486
    and audit["blinding_key_rows"] == 486
    and audit["unique_blind_ids_in_key"] == 486
    and audit["unique_run_ids_in_key"] == 486
    and not audit["blank_claim_texts"]
    and not audit["excluded_claims"]
    and not audit["non_contiguous_claim_id_summaries"]
    and set(by_blind) == set(key_blind_ids)
    and set(audit["summaries_per_policy"].values()) == {18}
    and set(audit["summaries_per_model"].values()) == {162}
    and set(audit["summaries_per_prompt_strategy"].values()) == {81}
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
print(json.dumps(audit, indent=2))

