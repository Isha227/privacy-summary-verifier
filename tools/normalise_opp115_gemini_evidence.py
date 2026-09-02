from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data/opp115/experiment/evaluations/faithfulness/gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"

with PATH.open(encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    rows = list(reader)
    fields = list(reader.fieldnames or [])

changed = 0
for row in rows:
    passages = [item.strip() for item in row.get("evidence_quote", "").split("\n---\n") if item.strip()]
    normalised = "\n---\n".join(dict.fromkeys(passages))
    if normalised != row.get("evidence_quote", ""):
        row["evidence_quote"] = normalised
        changed += 1

with PATH.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"Normalised {changed} evidence fields across {len(rows)} successful rows")

