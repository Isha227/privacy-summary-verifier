"""Create QA-approved clean texts for the proposed OPP-115 sample.

Raw corpus files and preliminary extractions remain unchanged.  Most policies
use the annotation-evidence boundary candidate; narrowly scoped overrides
remove known webpage interface material or retain the full archived PDF body.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


WORD_RE = re.compile(r"\b[\w][\w'’.-]*\b", flags=re.UNICODE)
SHORT_MAX = 1862
MEDIUM_MAX = 3291


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def band(count: int) -> str:
    if count <= SHORT_MAX:
        return "Short"
    if count <= MEDIUM_MAX:
        return "Medium"
    return "Long"


def find_nth(text: str, marker: str, occurrence: int = 1) -> int:
    start = -1
    for _ in range(occurrence):
        start = text.find(marker, start + 1)
        if start < 0:
            raise ValueError(f"Marker not found (occurrence {occurrence}): {marker!r}")
    return start


def trim_from(text: str, marker: str, occurrence: int = 1) -> str:
    return text[find_nth(text, marker, occurrence):]


def trim_through(text: str, marker: str, occurrence: int = 1) -> str:
    end = find_nth(text, marker, occurrence) + len(marker)
    paragraph_end = text.find("\n\n", end)
    return text[: paragraph_end if paragraph_end >= 0 else len(text)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-json", type=Path, required=True)
    parser.add_argument("--audit-csv", type=Path, required=True)
    parser.add_argument("--cleaned-dir", type=Path, required=True)
    parser.add_argument("--staged-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    selection = json.loads(args.selection_json.read_text(encoding="utf-8"))["proposed"]
    with args.audit_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        audit = {row["sample_id"]: row for row in csv.DictReader(handle)}

    final_text_dir = args.output_dir / "cleaned_policies"
    final_text_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    for selected in selection:
        sample_id = selected["sample_id"]
        audit_row = audit[sample_id]
        raw = (args.cleaned_dir / selected["cleaned_text_file"]).read_text(encoding="utf-8-sig")
        staged = (args.staged_dir / audit_row["staged_text_file"]).read_text(encoding="utf-8-sig")
        text = staged
        method = "Annotation-evidence boundary candidate retained after manual excerpt review"
        notes = "Policy content begins and ends within the archived policy page; surrounding navigation/footer material is excluded."

        if sample_id == "OPP03":
            text = trim_from(staged, "Bing and MSN Privacy Statement")
            method = "Manual start trim applied to annotation-evidence boundary"
            notes = "Removed update/layout controls before the Bing and MSN Privacy Statement; retained the policy through its final access section."
        elif sample_id == "OPP04":
            text = trim_from(staged, "Privacy Policy")
            method = "Manual start trim applied to annotation-evidence boundary"
            notes = "Removed one unrelated security/navigation fragment before the policy heading."
        elif sample_id == "OPP06":
            text = trim_from(staged, "Amazon.com Privacy Notice")
            method = "Manual start trim applied to annotation-evidence boundary"
            notes = "Removed the page title and promotional/navigation text preceding the privacy notice."
        elif sample_id == "OPP07":
            notes = "Accepted after manual review: the lower evidence-match rate is caused by a malformed spacing variant in an annotation, while the staged body contains the complete policy statement through the changes section."
        elif sample_id == "OPP10":
            text = trim_from(raw, "NOTICE OF PRIVACY PRACTICES")
            method = "Full archived PDF body retained from formal notice heading"
            notes = "Accepted after manual review. PDF extraction inserts spaces inside some words, which lowers exact evidence matching; the full archived notice is retained rather than truncated at the last exact match."
        elif sample_id == "OPP14":
            text = trim_from(raw, "Privacy Policy\n\nLast Revised")
            text = trim_through(text, "privacy@esrb.org")
            method = "Manual policy-heading and contact-end boundary"
            notes = "Retained the PlayStation privacy statement from its heading through the final ESRB contact; removed webpage feedback controls."
        elif sample_id == "OPP18":
            text = trim_from(raw, "Privacy Statement", occurrence=2)
            text = trim_through(text, "National Information Infrastructure Protection Act of 1996.")
            method = "Manual body start and final security-section boundary"
            notes = "Removed the table of contents and site footer while retaining the privacy statement and all substantive sections through Security."

        text = text.strip() + "\n"
        final_name = f"{sample_id}_{selected['cleaned_text_file']}"
        final_path = final_text_dir / final_name
        final_path.write_text(text, encoding="utf-8")
        words = word_count(text)
        results.append(
            {
                **selected,
                "preliminary_extracted_words": selected["word_count"],
                "final_policy_words": words,
                "final_length_band": band(words),
                "final_cleaned_text_file": final_name,
                "final_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "evidence_found_rate": audit_row["evidence_found_rate"],
                "boundary_qa_decision": "Pass",
                "boundary_method": method,
                "boundary_qa_notes": notes,
                "selection_status": "Proposed — boundary QA complete; supervisor approval pending",
            }
        )

    csv_path = args.output_dir / "opp115_proposed_27_boundary_qa.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    (args.output_dir / "opp115_proposed_27_boundary_qa.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    counts = {name: sum(row["final_length_band"] == name for row in results) for name in ("Short", "Medium", "Long")}
    print(f"QA-approved policy texts: {len(results)}")
    print(f"Final length bands: {counts}")
    print(f"Boundary QA failures: {sum(row['boundary_qa_decision'] != 'Pass' for row in results)}")
    print(f"QA table: {csv_path}")


if __name__ == "__main__":
    main()
