from __future__ import annotations

import csv
import re
from pathlib import Path

from .common import ROOT, load_config, sha256_text, write_json


FIELDS = [
    "blind_id", "statement_id", "statement_text", "include", "review_notes",
]


def split_sentences(text: str) -> list[str]:
    """Deterministic sentence split for prose-only v2 summaries."""
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip()
    ]


def prepare_one(blind_id: str) -> tuple[int, Path]:
    cfg = load_config()
    settings = cfg["v2_statements"]
    summary_path = ROOT / cfg["paths"]["anonymised"] / f"{blind_id}.txt"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing blinded summary: {summary_path}")

    summary = summary_path.read_text(encoding="utf-8").strip()
    statements = split_sentences(summary)
    if not statements:
        raise ValueError(f"No summary statements found for {blind_id}")

    output_dir = ROOT / settings["output_dir"] / blind_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{blind_id}_summary_statements_v{settings['version']}.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for number, statement in enumerate(statements, 1):
            writer.writerow({
                "blind_id": blind_id,
                "statement_id": f"{blind_id}-ST{number:03d}",
                "statement_text": statement,
                "include": "yes",
                "review_notes": "",
            })

    write_json(output_dir / f"{blind_id}_summary_statements_v{settings['version']}_audit.json", {
        "blind_id": blind_id,
        "splitter_version": str(settings["version"]),
        "split_rule": "(?<=[.!?])\\s+|\\n+",
        "summary_sha256": sha256_text(summary),
        "statement_count": len(statements),
    })
    return len(statements), output_path
