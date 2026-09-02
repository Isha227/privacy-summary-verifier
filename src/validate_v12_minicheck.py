from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from .common import ROOT, read_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=(
        "data/v2_prompt_intervention_v1_2/minicheck_colab/"
        "MSc_AI_MiniCheck_V12/minicheck_v12_statement_scores_FINAL.csv"
    ))
    args = parser.parse_args()
    path = ROOT / args.path
    rows = read_csv(path)
    expected_path = ROOT / "data/v2_prompt_intervention_v1_2/minicheck_colab/v12_minicheck_statements.csv"
    expected = {row["statement_id"]: row for row in read_csv(expected_path)}

    errors: list[str] = []
    ids = [row.get("statement_id", "") for row in rows]
    if len(rows) != 1393:
        errors.append(f"Expected 1393 rows; found {len(rows)}")
    if len(set(ids)) != len(ids):
        errors.append(f"Duplicate statement IDs: {len(ids) - len(set(ids))}")
    if set(ids) != set(expected):
        errors.append(f"Missing={len(set(expected)-set(ids))}; unexpected={len(set(ids)-set(expected))}")
    if len({row.get("blind_id", "") for row in rows}) != 54:
        errors.append(f"Expected 54 summaries; found {len({row.get('blind_id','') for row in rows})}")
    failed = [row for row in rows if row.get("status") != "success"]
    if failed:
        errors.append(f"Non-success rows: {len(failed)}")
    models = {row.get("minicheck_model", "") for row in rows}
    if models != {"flan-t5-large"}:
        errors.append(f"Unexpected model IDs: {sorted(models)}")
    labels = {row.get("predicted_supported", "") for row in rows}
    if not labels <= {"0", "1"}:
        errors.append(f"Unexpected labels: {sorted(labels)}")
    for row in rows:
        statement_id = row.get("statement_id", "")
        exp = expected.get(statement_id)
        if exp and any(row.get(field, "") != exp.get(field, "") for field in ("blind_id", "policy_id", "statement_text")):
            errors.append(f"Frozen input mismatch: {statement_id}")
            break
        try:
            probability = float(row.get("probability", ""))
            if not 0.0 <= probability <= 1.0:
                raise ValueError
        except ValueError:
            errors.append(f"Invalid probability: {statement_id}")
            break

    print(f"Rows: {len(rows)}")
    print(f"Unique statements: {len(set(ids))}")
    print(f"Summaries represented: {len({row.get('blind_id','') for row in rows})}")
    print(f"Successful: {len(rows)-len(failed)}")
    print(f"Model IDs: {sorted(models)}")
    print(f"Predictions: {dict(Counter(row.get('predicted_supported','') for row in rows))}")
    if errors:
        for error in errors:
            print("ERROR:", error)
        raise SystemExit(1)
    print("VALID: MiniCheck v1.2 result matches the frozen evaluator input exactly.")


if __name__ == "__main__":
    main()
