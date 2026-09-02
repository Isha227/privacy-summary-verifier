"""Propose auditable policy-body boundaries using OPP annotation evidence.

The script does not alter the raw corpus or the preliminary extracted texts. It
writes staged boundary candidates and a QA table for manual review.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


WORD_RE = re.compile(r"\b[\w][\w'’.-]*\b", flags=re.UNICODE)
QUOTE_MAP = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalise_with_map(text: str) -> tuple[str, list[int]]:
    output: list[str] = []
    source_map: list[int] = []
    previous_space = False
    for index, char in enumerate(text.translate(QUOTE_MAP)):
        if char.isspace():
            if output and not previous_space:
                output.append(" ")
                source_map.append(index)
            previous_space = True
            continue
        output.append(char.casefold())
        source_map.append(index)
        previous_space = False
    if output and output[-1] == " ":
        output.pop()
        source_map.pop()
    return "".join(output), source_map


def normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(QUOTE_MAP)).strip().casefold()


def selected_texts(annotation_path: Path) -> list[str]:
    values: set[str] = set()
    with annotation_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 7:
                continue
            try:
                attributes = json.loads(row[6])
            except json.JSONDecodeError:
                continue
            for attribute in attributes.values():
                value = attribute.get("selectedText") if isinstance(attribute, dict) else None
                if isinstance(value, str) and len(normalise(value)) >= 15:
                    values.add(value)
    return sorted(values, key=lambda value: (len(value), value))


def expand_start(text: str, position: int) -> int:
    paragraph = text.rfind("\n\n", 0, position)
    if paragraph >= 0:
        return paragraph + 2
    line = text.rfind("\n", 0, position)
    return line + 1 if line >= 0 else 0


def expand_end(text: str, position: int) -> int:
    paragraph = text.find("\n\n", position)
    if paragraph >= 0:
        return paragraph
    line = text.find("\n", position)
    return line if line >= 0 else len(text)


def context(text: str, position: int, radius: int = 280) -> str:
    start = max(0, position - radius)
    end = min(len(text), position + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-json", type=Path, required=True)
    parser.add_argument("--cleaned-dir", type=Path, required=True)
    parser.add_argument("--consolidation-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    selection = json.loads(args.selection_json.read_text(encoding="utf-8"))["proposed"]
    staged_dir = args.output_dir / "staged_policy_bodies"
    staged_dir.mkdir(parents=True, exist_ok=True)
    audit_rows: list[dict[str, object]] = []

    for row in selection:
        uid = int(row["opp_policy_uid"])
        source_path = args.cleaned_dir / row["cleaned_text_file"]
        annotation_matches = list(args.consolidation_dir.glob(f"{uid}_*.csv"))
        if len(annotation_matches) != 1:
            raise ValueError(f"Expected one consolidation file for OPP UID {uid}; found {len(annotation_matches)}")

        text = source_path.read_text(encoding="utf-8-sig")
        normalised_text, source_map = normalise_with_map(text)
        evidence = selected_texts(annotation_matches[0])
        matches: list[tuple[int, int, str]] = []
        missed: list[str] = []
        for item in evidence:
            needle = normalise(item)
            position = normalised_text.find(needle)
            if position < 0:
                missed.append(item)
                continue
            source_start = source_map[position]
            source_end = source_map[min(position + len(needle) - 1, len(source_map) - 1)] + 1
            matches.append((source_start, source_end, item))

        if not matches:
            proposed_start, proposed_end = 0, len(text)
        else:
            proposed_start = expand_start(text, min(match[0] for match in matches))
            proposed_end = expand_end(text, max(match[1] for match in matches))

        staged = text[proposed_start:proposed_end].strip() + "\n"
        staged_path = staged_dir / f"{row['sample_id']}_{row['cleaned_text_file']}"
        staged_path.write_text(staged, encoding="utf-8")

        first_match = min(matches, default=(0, 0, ""), key=lambda value: value[0])
        last_match = max(matches, default=(0, 0, ""), key=lambda value: value[1])
        raw_words = len(WORD_RE.findall(text))
        staged_words = len(WORD_RE.findall(staged))
        audit_rows.append(
            {
                "sample_id": row["sample_id"],
                "opp_policy_uid": uid,
                "organisation": row["organisation"],
                "raw_extracted_words": raw_words,
                "proposed_policy_words": staged_words,
                "removed_prefix_words": len(WORD_RE.findall(text[:proposed_start])),
                "removed_suffix_words": len(WORD_RE.findall(text[proposed_end:])),
                "unique_annotation_evidence": len(evidence),
                "evidence_found": len(matches),
                "evidence_not_found": len(missed),
                "evidence_found_rate": round(len(matches) / len(evidence), 6) if evidence else 0,
                "first_evidence_excerpt": context(text, first_match[0]),
                "last_evidence_excerpt": context(text, last_match[1]),
                "first_missing_evidence": re.sub(r"\s+", " ", missed[0]).strip()[:500] if missed else "",
                "staged_text_file": staged_path.name,
                "automatic_boundary_status": (
                    "Review"
                    if not evidence or len(matches) / len(evidence) < 0.90 or staged_words < 250
                    else "Candidate pass"
                ),
                "manual_qa_decision": "Pending",
                "manual_qa_notes": "",
            }
        )

    output_csv = args.output_dir / "opp115_boundary_audit.csv"
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    (args.output_dir / "opp115_boundary_audit.json").write_text(
        json.dumps(audit_rows, indent=2), encoding="utf-8"
    )

    print(f"Audited policies: {len(audit_rows)}")
    print(f"Candidate pass: {sum(row['automatic_boundary_status'] == 'Candidate pass' for row in audit_rows)}")
    print(f"Review required: {sum(row['automatic_boundary_status'] == 'Review' for row in audit_rows)}")
    print(f"Audit: {output_csv}")


if __name__ == "__main__":
    main()
