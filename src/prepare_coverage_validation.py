"""Prepare independent main-study source-unit packages for coverage validation."""

from __future__ import annotations

import csv
import hashlib
import shutil
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "data" / "main" / "metadata" / "policies.csv"

CATEGORIES = [
    ("C1", "Data Collection & Sources"),
    ("C2", "Purpose & Legal Basis"),
    ("C3", "Data Sharing & Recipients"),
    ("C4", "Data Retention"),
    ("C5", "User Rights & Controls"),
    ("C6", "Tracking, Profiling & Automated Processing"),
    ("C7", "International Transfers"),
    ("C8", "Data Security"),
    ("C9", "Contact, Complaints & Policy Administration"),
]

FIELDS = [
    "annotator_id",
    "policy_id",
    "unit_id",
    "category",
    "source_section",
    "source_quote_or_locator",
    "information_unit",
    "material_qualifiers",
    "notes",
]


def instructions(annotator: str, policy_id: str) -> str:
    category_lines = "\n".join(f"- `{code}` — {name}" for code, name in CATEGORIES)
    return f"""# {policy_id} source-unit annotation — {annotator}

## Your task

Read `{policy_id}_source.txt` and complete `source_units_{policy_id}_{annotator}.csv`.
Add one row for every distinct, important privacy-information proposition in
the policy. Work independently and do not open any generated summaries,
faithfulness results, blinding keys, or another evaluator's file.

## Frozen categories

{category_lines}

Children, sensitive data, consent, cookies, advertising, policy changes and
business closure are conditional subtopics inside the most appropriate frozen
category; do not create new top-level categories.

## Unit rule

A unit is one independently scorable proposition whose omission or distortion
would remove meaningful privacy information. Keep connected qualifiers in the
same unit and record them in `material_qualifiers`. Split propositions only
when a later summary could reasonably preserve one while omitting another.

Use provisional IDs such as `{annotator}-C1-U01`, `{annotator}-C1-U02`, then
restart numbering within each category. Use a short source quotation or a
heading plus distinctive phrase as the locator. Include only information that
is explicit in the frozen source.

## Important safeguards

- Do not reward repetition by creating duplicate units.
- Do not create a unit merely because a topic could have appeared.
- Negative statements (for example, data is not sold) may be material units.
- Preserve durations, recipient scope, exceptions, legal conditions and
  opt-out limitations as material qualifiers.
- Do not copy whole paragraphs as units; write short factual propositions.
- Do not discuss your list with A1/A2/A3 until all three files are complete.

## When finished

Save the completed CSV in this folder without changing its filename. Tell the
project lead: `{annotator} {policy_id} source units done`. Do not start coverage
scoring yet. The three lists must first be aligned, adjudicated and frozen.
"""


def write_blank(path: Path, annotator: str, policy_id: str) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for code, _ in CATEGORIES:
            writer.writerow(
                {
                    "annotator_id": annotator,
                    "policy_id": policy_id,
                    "unit_id": f"{annotator}-{code}-U01",
                    "category": code,
                    "notes": "Delete this starter row if the policy contains no applicable unit; otherwise complete it and add rows.",
                }
            )


def metadata_for(policy_id: str) -> dict[str, str]:
    with METADATA.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["policy_id"].strip().upper() == policy_id:
                return row
    raise ValueError(f"Policy not found in metadata: {policy_id}")


def prepare(policy_id: str) -> None:
    policy_id = policy_id.strip().upper()
    source = ROOT / "data" / "main" / "clean" / f"{policy_id}.txt"
    base = ROOT / "data" / "main" / "coverage_validation" / policy_id
    if not source.exists():
        raise FileNotFoundError(source)
    source_text = source.read_text(encoding="utf-8")
    metadata = metadata_for(policy_id)
    base.mkdir(parents=True, exist_ok=True)

    for annotator in ("A1", "A2", "A3"):
        package = base / f"Source_Unit_Annotator_{annotator}_Package"
        package.mkdir(parents=True, exist_ok=True)
        destination = package / f"source_units_{policy_id}_{annotator}.csv"
        if destination.exists():
            raise FileExistsError(
                f"Refusing to overwrite an existing annotation file: {destination}"
            )
        shutil.copyfile(source, package / f"{policy_id}_source.txt")
        write_blank(destination, annotator, policy_id)
        (package / "INSTRUCTIONS.md").write_text(
            instructions(annotator, policy_id), encoding="utf-8"
        )

    manifest = base / "VALIDATION_MANIFEST.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["policy_id", "organisation", "sector", "source_words", "source_sha256", "annotators", "stage"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "policy_id": policy_id,
                "organisation": metadata["organisation"],
                "sector": metadata["sector"],
                "source_words": len(source_text.split()),
                "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                "annotators": "A1;A2;A3",
                "stage": "independent_source_unit_annotation",
            }
        )

    print(f"Prepared coverage validation policy: {policy_id}")
    print(f"Source words: {len(source_text.split())}")
    print(f"Packages: {base}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy_ids", nargs="+", help="Policy IDs, for example MAIN03 MAIN23")
    args = parser.parse_args()
    for policy_id in args.policy_ids:
        prepare(policy_id)


if __name__ == "__main__":
    main()
