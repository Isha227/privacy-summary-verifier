from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLIND_ID = "S001"
KEY_PATH = ROOT / "data/opp115/experiment/anonymised/BLINDING_KEY_RESTRICTED.csv"
RESULT_PATH = ROOT / "data/opp115/experiment/evaluations/faithfulness/gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


mapping = {row["blind_id"]: row for row in read(KEY_PATH)}
rows = [row for row in read(RESULT_PATH) if row["blind_id"] == BLIND_ID and row["status"] == "success"]
policy_id = mapping[BLIND_ID]["policy_id"]
source = (ROOT / "data/opp115/frozen/clean" / f"{policy_id}.txt").read_text(encoding="utf-8")

valid_labels = {"Supported", "Partially supported", "Unsupported", "Contradicted"}
evidence_rows = [row for row in rows if row["evidence_quote"].strip()]


def exact_evidence(row: dict[str, str]) -> bool:
    passages = [item.strip() for item in row["evidence_quote"].split("\n---\n") if item.strip()]
    return bool(passages) and all(passage in source for passage in passages)

print(f"policy={policy_id}")
print(f"successful_rows={len(rows)}")
print(f"unique_claim_ids={len({row['claim_id'] for row in rows})}")
print(f"labels={dict(Counter(row['label'] for row in rows))}")
print(f"invalid_labels={sum(row['label'] not in valid_labels for row in rows)}")
print(f"blank_explanations={sum(not row['explanation'].strip() for row in rows)}")
print(f"blank_nonunsupported_evidence={sum(row['label'] != 'Unsupported' and not row['evidence_quote'].strip() for row in rows)}")
print(f"exact_evidence_rows={sum(exact_evidence(row) for row in evidence_rows)}/{len(evidence_rows)}")

for row in rows:
    print(f"{row['claim_id']} | {row['label']} | {row['evidence_quote'][:90]} | {row['explanation'][:120]}")
    if row["evidence_quote"].strip() and not exact_evidence(row):
        print(f"  NON-EXACT: {row['evidence_quote']!r}")
