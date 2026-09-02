"""Create the proposed balanced 27-policy OPP-115 sample metadata."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SHORT_MAX = 1862
MEDIUM_MAX = 3291


SELECTION = [
    # Technology and social platforms
    (1361, "Yahoo", "Technology and social platforms"),
    (135, "Instagram", "Technology and social platforms"),
    (1582, "Microsoft", "Technology and social platforms"),
    # Retail and e-commerce
    (807, "Lodge Manufacturing", "Retail and e-commerce"),
    (1694, "Lids", "Retail and e-commerce"),
    (105, "Amazon", "Retail and e-commerce"),
    # News and digital media
    (164, "Adweek", "News and digital media"),
    (32, "Vox Media", "News and digital media"),
    (1713, "Latin Post", "News and digital media"),
    # Health and medical information
    (517, "Kaleida Health", "Health and medical information"),
    (202, "Food Allergy Research & Education", "Health and medical information"),
    (891, "Everyday Health", "Health and medical information"),
    # Gaming and interactive entertainment
    (456, "BoardGameGeek", "Gaming and interactive entertainment"),
    (635, "PlayStation", "Gaming and interactive entertainment"),
    (1468, "Rockstar Games", "Gaming and interactive entertainment"),
    # Government and civic information
    (559, "Library of Congress", "Government and civic information"),
    (1264, "Public Citizen", "Government and civic information"),
    (531, "US National Archives", "Government and civic information"),
    # Food and hospitality
    (627, "Dairy Queen", "Food and hospitality"),
    (746, "Kraft Recipes", "Food and hospitality"),
    (70, "Allrecipes", "Food and hospitality"),
    # Travel, leisure and sport
    (1703, "Sports Reference", "Travel, leisure and sport"),
    (1539, "Geocaching", "Travel, leisure and sport"),
    (175, "Major League Baseball", "Travel, leisure and sport"),
    # Finance, payments and insurance
    (1261, "Zacks Investment Research", "Finance, payments and insurance"),
    (1306, "Chase Paymentech", "Finance, payments and insurance"),
    (1106, "Allstate", "Finance, payments and insurance"),
]


def band(word_count: int) -> str:
    if word_count <= SHORT_MAX:
        return "Short"
    if word_count <= MEDIUM_MAX:
        return "Medium"
    return "Long"


def annotation_rows(consolidation_dir: Path, uid: int) -> int:
    matches = list(consolidation_dir.glob(f"{uid}_*.csv"))
    if len(matches) != 1:
        return 0
    with matches[0].open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return sum(1 for _ in csv.reader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--consolidation-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    with args.catalogue.open("r", encoding="utf-8-sig", newline="") as handle:
        catalogue = list(csv.DictReader(handle))

    by_uid = {int(row["policy_uid"]): row for row in catalogue}
    selected_lookup = {uid: (organisation, sector) for uid, organisation, sector in SELECTION}

    all_rows: list[dict[str, object]] = []
    for row in catalogue:
        uid = int(row["policy_uid"])
        words = int(row["word_count"])
        organisation, sector = selected_lookup.get(uid, ("", ""))
        all_rows.append(
            {
                **row,
                "length_band": band(words),
                "selected": "Yes" if uid in selected_lookup else "No",
                "organisation": organisation,
                "sector": sector,
            }
        )

    proposed: list[dict[str, object]] = []
    for index, (uid, organisation, sector) in enumerate(SELECTION, start=1):
        source = by_uid[uid]
        words = int(source["word_count"])
        proposed.append(
            {
                "sample_id": f"OPP{index:02d}",
                "opp_policy_uid": uid,
                "organisation": organisation,
                "sector": sector,
                "domain": source["domain"],
                "word_count": words,
                "length_band": band(words),
                "collection_date": source["collection_date"],
                "last_updated_date": source["last_updated_date"],
                "policy_url": source["policy_url"],
                "cleaned_text_file": source["cleaned_text_file"],
                "consolidated_annotation_rows": annotation_rows(args.consolidation_dir, uid),
                "selection_status": "Proposed — not frozen",
                "text_qa_status": "Preliminary extraction; boundary QA required",
                "selection_rationale": (
                    f"Adds a {band(words).lower()} historical privacy policy from the "
                    f"{sector.lower()} sector while supporting the 9/9/9 overall length balance."
                ),
            }
        )

    write_csv(args.output_dir / "opp115_all_policies_with_bands.csv", all_rows)
    write_csv(args.output_dir / "opp115_proposed_27.csv", proposed)
    (args.output_dir / "opp115_selection_data.json").write_text(
        json.dumps({"all_policies": all_rows, "proposed": proposed}, indent=2),
        encoding="utf-8",
    )

    counts: dict[str, int] = {"Short": 0, "Medium": 0, "Long": 0}
    for row in proposed:
        counts[str(row["length_band"])] += 1
    print(f"Proposed policies: {len(proposed)}")
    print(f"Length bands: {counts}")
    print(f"Sectors: {len(set(row['sector'] for row in proposed))}")


if __name__ == "__main__":
    main()
