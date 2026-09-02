from __future__ import annotations

import csv

from .common import ROOT, read_csv


FIELDS = [
    "policy_id", "unit_id", "category", "information_unit",
    "material_qualifiers", "adjudication_source", "status",
]


def finalise() -> tuple[int, object]:
    base = ROOT / "data" / "pilot" / "metadata"
    source = base / "source_unit_adjudication_PILOT03.csv"
    destination = base / "source_units_PILOT03.csv"
    adjudication = read_csv(source)
    retained = [row for row in adjudication if row.get("adjudication_decision", "").strip().lower() == "retain"]
    rows = []
    seen = set()
    for row in retained:
        unit_id = row.get("final_unit_id", "").strip()
        information = row.get("final_information_unit", "").strip()
        if not unit_id or not information:
            raise ValueError(f"Incomplete retained row: {row.get('provisional_unit_id')}")
        if unit_id in seen:
            raise ValueError(f"Duplicate final unit ID: {unit_id}")
        seen.add(unit_id)
        category = unit_id.split("-")[1]
        rows.append({
            "policy_id": "PILOT03", "unit_id": unit_id, "category": category,
            "information_unit": information,
            "material_qualifiers": row.get("final_material_qualifiers", "").strip(),
            "adjudication_source": row.get("provisional_unit_id", ""), "status": "active",
        })
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), destination


if __name__ == "__main__":
    count, path = finalise()
    print(f"Finalised {count} PILOT03 source units: {path}")
