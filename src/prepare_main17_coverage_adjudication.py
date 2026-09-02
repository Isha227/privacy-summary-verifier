"""Align MAIN17 source units for human adjudication without changing originals."""

from __future__ import annotations

import csv
import math
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "main" / "coverage_validation" / "MAIN17"

FIELDS = [
    "policy_id", "candidate_id", "category",
    "a1_unit_id", "a1_information_unit", "a1_material_qualifiers",
    "a2_unit_id", "a2_information_unit", "a2_material_qualifiers",
    "a3_unit_id", "a3_information_unit", "a3_material_qualifiers",
    "candidate_similarity_note", "agreement_status", "adjudication_decision",
    "final_unit_id", "final_information_unit", "final_material_qualifiers", "rationale",
]

STOP = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "is", "are",
    "that", "this", "with", "we", "you", "your", "may", "can", "will", "be",
    "by", "from", "as", "at", "it", "its", "their", "they", "our", "any",
}


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def vector(row: dict) -> Counter:
    text = " ".join(
        [
            row.get("source_section", ""),
            row.get("source_quote_or_locator", ""),
            row.get("information_unit", ""),
            row.get("material_qualifiers", ""),
        ]
    ).lower()
    return Counter(
        word for word in re.findall(r"[a-z0-9]+", text)
        if len(word) > 2 and word not in STOP
    )


def cosine(left: dict, right: dict) -> float:
    a, b = vector(left), vector(right)
    common = set(a) & set(b)
    numerator = sum(a[word] * b[word] for word in common)
    denominator = math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))
    return numerator / denominator if denominator else 0.0


def best(anchor: dict, pool: list[dict], used: set[str], threshold: float = 0.22):
    candidates = [
        row for row in pool
        if row["category"] == anchor["category"] and row["unit_id"] not in used
    ]
    if not candidates:
        return None, 0.0
    score, row = max(
        ((cosine(anchor, row), row) for row in candidates),
        key=lambda item: item[0],
    )
    return (row, score) if score >= threshold else (None, score)


def columns(prefix: str, row: dict | None) -> dict:
    if row is None:
        return {
            f"{prefix}_unit_id": "",
            f"{prefix}_information_unit": "",
            f"{prefix}_material_qualifiers": "",
        }
    return {
        f"{prefix}_unit_id": row["unit_id"],
        f"{prefix}_information_unit": row["information_unit"],
        f"{prefix}_material_qualifiers": row.get("material_qualifiers", ""),
    }


def main() -> None:
    a1 = read(BASE / "Source_Unit_Annotator_A1_Package" / "source_units_MAIN17_A1.csv")
    a2 = read(BASE / "Source_Unit_Annotator_A2_Package" / "source_units_MAIN17_A2.csv")
    a3 = read(BASE / "Source_Unit_Annotator_A3_Package" / "source_units_MAIN17_A3.csv")
    used1: set[str] = set()
    used3: set[str] = set()
    rows: list[dict] = []

    def append(one=None, two=None, three=None, note=""):
        present = sum(item is not None for item in (one, two, three))
        rows.append(
            {
                "policy_id": "MAIN17",
                "candidate_id": f"M17-ADJ-{len(rows)+1:03d}",
                "category": (two or one or three)["category"],
                **columns("a1", one), **columns("a2", two), **columns("a3", three),
                "candidate_similarity_note": note,
                "agreement_status": (
                    "three-way candidate alignment — review required" if present == 3
                    else "two-way candidate alignment — review required" if present == 2
                    else "unique candidate — review required"
                ),
                "adjudication_decision": "",
                "final_unit_id": "",
                "final_information_unit": "",
                "final_material_qualifiers": "",
                "rationale": "",
            }
        )

    # Use recalibrated A2 as the median-size anchor list.
    for anchor in a2:
        one, score1 = best(anchor, a1, used1)
        three, score3 = best(anchor, a3, used3)
        if one:
            used1.add(one["unit_id"])
        if three:
            used3.add(three["unit_id"])
        append(one, anchor, three, f"A2-A1={score1:.3f}; A2-A3={score3:.3f}")

    # Align residual A1 and A3 candidates, then retain unmatched A3 rows.
    for anchor in [row for row in a1 if row["unit_id"] not in used1]:
        three, score3 = best(anchor, a3, used3)
        if three:
            used3.add(three["unit_id"])
        append(anchor, None, three, f"residual A1-A3={score3:.3f}")
    for anchor in [row for row in a3 if row["unit_id"] not in used3]:
        append(None, None, anchor, "unmatched A3 candidate")

    destination = BASE / "source_unit_adjudication_MAIN17.csv"
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    guide = BASE / "ADJUDICATION_INSTRUCTIONS.md"
    guide.write_text(
        """# MAIN17 source-unit adjudication

The candidate matches in `source_unit_adjudication_MAIN17.csv` were produced
automatically to reduce clerical work. They are not final decisions and may be
wrong, especially where one researcher split a broad unit into several units.

The three researchers should now review every row together while consulting
`MAIN17_source.txt`. For each row:

1. Correct any false alignment by moving/copying the relevant wording to a new
   row and leaving a clear rationale.
2. Set `agreement_status` to `unanimous`, `boundary disagreement`, `category
   disagreement`, `wording disagreement`, or `unique unit`.
3. Set `adjudication_decision` to `retain`, `merge`, `split`, or `exclude`.
4. For every retained final proposition, assign the next ID within its category
   (for example `M17-C1-U01`) and complete the final wording and qualifiers.
5. Explain exclusions, merges and non-obvious boundary decisions in `rationale`.

Use one row per final independently scorable proposition. If an aligned row
contains two final propositions, insert a second row and mark both as `split`.
Do not view generated summaries during adjudication. The completed final-unit
columns will become the frozen denominator used for all nine MAIN17 summaries.
""",
        encoding="utf-8",
    )
    print(f"Prepared {len(rows)} candidate rows: {destination}")
    print(f"Three-way: {sum(r['agreement_status'].startswith('three') for r in rows)}")
    print(f"Two-way: {sum(r['agreement_status'].startswith('two') for r in rows)}")
    print(f"Unique: {sum(r['agreement_status'].startswith('unique') for r in rows)}")


if __name__ == "__main__":
    main()
