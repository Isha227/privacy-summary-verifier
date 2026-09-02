from __future__ import annotations

import csv
from pathlib import Path

from .common import ROOT, load_config, read_csv
from .v2_statements import prepare_one


def prepare_all() -> tuple[int, int, Path]:
    cfg = load_config()
    key_path = ROOT / cfg["paths"]["anonymised"] / "BLINDING_KEY_RESTRICTED.csv"
    key = read_csv(key_path)
    if len(key) != 54:
        raise RuntimeError(f"Expected 54 blinded summaries; found {len(key)}")

    manifest_rows = []
    statement_total = 0
    for row in sorted(key, key=lambda item: item["blind_id"]):
        count, path = prepare_one(row["blind_id"])
        statement_total += count
        manifest_rows.append({
            "blind_id": row["blind_id"],
            "policy_id": row["policy_id"],
            "statement_count": count,
            "statement_file": path.relative_to(ROOT).as_posix(),
        })

    output = ROOT / cfg["v2_evaluation"]["root"] / "evaluations" / "evaluation_manifest_restricted.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)
    return len(key), statement_total, output


if __name__ == "__main__":
    summaries, statements, path = prepare_all()
    print(f"Prepared {statements} statements from {summaries} blinded summaries: {path}")
