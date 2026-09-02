from __future__ import annotations

import csv
import json
from collections import Counter

from .common import ROOT, load_config, read_csv


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    cfg = load_config()
    root = ROOT / cfg["v2_evaluation"]["root"] / "evaluations"
    statements = [row for path in sorted((root / "gemini_statement_verification").glob("*/S*_statement_verification_v1.3.csv")) for row in read_csv(path)]
    coverage = [row for path in sorted((root / "gemini_preliminary_coverage").glob("*/S*_gemini_coverage_v1.0.csv")) for row in read_csv(path)]
    statement_path = root / "gemini_statement_verification_all.csv"
    coverage_path = root / "gemini_preliminary_coverage_all.csv"
    write(statement_path, statements); write(coverage_path, coverage)
    summary = {
        "gemini_model": cfg["v2_statement_verifier"]["model"],
        "statement_rows": len(statements),
        "statement_summaries": len({r["blind_id"] for r in statements}),
        "statement_labels": dict(Counter(r["label"] for r in statements)),
        "failure_types": dict(Counter(r["failure_type"] for r in statements)),
        "coverage_comparisons": len(coverage),
        "coverage_summaries": len({r["blind_id"] for r in coverage}),
        "coverage_labels": dict(Counter(r["coverage_label"] for r in coverage)),
        "evidence_invalid_rows": sum(r["status"] != "success" for r in statements + coverage),
        "coverage_scope": "preliminary Gemini-only units; repeat on human-adjudicated shared units for agreement",
    }
    summary_path = root / "gemini_v12_completion_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(statement_path); print(coverage_path); print(summary_path)


if __name__ == "__main__":
    main()
