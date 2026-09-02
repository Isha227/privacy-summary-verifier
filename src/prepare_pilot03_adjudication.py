from __future__ import annotations

import csv
import math
import re
from collections import Counter
from pathlib import Path

from .common import ROOT, read_csv


FIELDS = [
    "policy_id", "provisional_unit_id", "category", "annotator_1_unit",
    "annotator_2_unit", "annotator_3_unit", "candidate_similarity_note",
    "agreement_status", "adjudication_decision", "final_unit_id",
    "final_information_unit", "final_material_qualifiers", "rationale",
]


def tokens(row: dict) -> Counter:
    text = " ".join([
        row.get("source_section", ""), row.get("source_quote_or_locator", ""),
        row.get("information_unit", ""), row.get("material_qualifiers", ""),
    ]).lower()
    words = re.findall(r"[a-z0-9]+", text)
    stop = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "is", "are", "that", "this", "with", "we", "you", "your"}
    return Counter(word for word in words if word not in stop and len(word) > 2)


def cosine(left: Counter, right: Counter) -> float:
    common = set(left) & set(right)
    numerator = sum(left[word] * right[word] for word in common)
    denominator = math.sqrt(sum(v * v for v in left.values()) * sum(v * v for v in right.values()))
    return numerator / denominator if denominator else 0.0


def best_unused(anchor: dict, candidates: list[dict], used: set[str]) -> tuple[dict | None, float]:
    eligible = [row for row in candidates if row["category"] == anchor["category"] and row["unit_id"] not in used]
    if not eligible:
        return None, 0.0
    scored = [(cosine(tokens(anchor), tokens(row)), row) for row in eligible]
    score, row = max(scored, key=lambda item: item[0])
    return (row, score) if score >= 0.20 else (None, score)


def prepare() -> tuple[int, Path]:
    base = ROOT / "data" / "pilot" / "metadata"
    a1 = read_csv(base / "source_units_PILOT03_A1.csv")
    a2 = read_csv(base / "source_units_PILOT03_A2.csv")
    a3 = read_csv(base / "source_units_PILOT03_A3.csv")
    used2: set[str] = set()
    used3: set[str] = set()
    rows: list[dict] = []

    def add(category: str, one: str = "", two: str = "", three: str = "", scores: str = "") -> None:
        number = len(rows) + 1
        rows.append({
            "policy_id": "PILOT03", "provisional_unit_id": f"ADJ3-{number:03d}",
            "category": category, "annotator_1_unit": one, "annotator_2_unit": two,
            "annotator_3_unit": three, "candidate_similarity_note": scores,
            "agreement_status": "candidate alignment — review required",
            "adjudication_decision": "", "final_unit_id": "",
            "final_information_unit": "", "final_material_qualifiers": "", "rationale": "",
        })

    for anchor in a1:
        match2, score2 = best_unused(anchor, a2, used2)
        match3, score3 = best_unused(anchor, a3, used3)
        if match2:
            used2.add(match2["unit_id"])
        if match3:
            used3.add(match3["unit_id"])
        add(anchor["category"], anchor["unit_id"], match2["unit_id"] if match2 else "",
            match3["unit_id"] if match3 else "", f"A1-A2={score2:.3f}; A1-A3={score3:.3f}")

    for anchor in [row for row in a2 if row["unit_id"] not in used2]:
        match3, score3 = best_unused(anchor, a3, used3)
        if match3:
            used3.add(match3["unit_id"])
        add(anchor["category"], "", anchor["unit_id"], match3["unit_id"] if match3 else "",
            f"A2-A3={score3:.3f}")

    for anchor in [row for row in a3 if row["unit_id"] not in used3]:
        add(anchor["category"], "", "", anchor["unit_id"], "unmatched A3 candidate")

    destination = base / "source_unit_adjudication_PILOT03.csv"
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), destination


if __name__ == "__main__":
    count, path = prepare()
    print(f"Prepared {count} candidate adjudication rows: {path}")
