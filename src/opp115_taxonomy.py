from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

from .common import ROOT, load_config, read_csv, write_json


RAW = ROOT / "data/opp115/raw/OPP-115_v1_0/OPP-115/consolidation/threshold-0.75-overlap-similarity"
BASE = ROOT / "data/opp115/experiment/coverage_v3"
FROZEN_UNITS = BASE / "source_units/frozen_source_units.csv"
FROZEN_MANIFEST = BASE / "source_units/frozen_source_units_manifest.json"
OUTPUT = BASE / "taxonomy/opp115_unit_taxonomy_candidates.csv"
AUDIT = BASE / "taxonomy/opp115_unit_taxonomy_candidates_audit.json"


FIELDS = [
    "policy_id", "unit_id", "important_information", "opp_category",
    "annotation_id", "annotation_selected_text", "overlap_method",
    "token_containment", "token_jaccard", "review_decision", "review_notes",
]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in _normalise(text).split() if len(token) > 1}


def _selected_texts(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "selectedText" and isinstance(item, str) and item.strip():
                found.append(item.strip())
            else:
                found.extend(_selected_texts(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_selected_texts(item))
    return found


def _annotation_file(uid: str) -> Path:
    matches = sorted(RAW.glob(f"{uid}_*.csv"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one consolidated annotation file for OPP UID {uid}, found {len(matches)}")
    return matches[0]


def prepare() -> dict:
    if not FROZEN_UNITS.is_file() or not FROZEN_MANIFEST.is_file():
        raise RuntimeError(
            "Taxonomy comparison is locked until all independently generated source units are frozen"
        )
    manifest = json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen" or manifest.get("policies") != 27:
        raise RuntimeError("The source-unit manifest is not a valid 27-policy freeze")

    cfg = load_config()
    metadata = {row["policy_id"]: row for row in read_csv(ROOT / cfg["paths"]["metadata"])}
    units = read_csv(FROZEN_UNITS)
    annotations: dict[str, list[dict]] = {}
    annotation_counts = {}
    for policy_id, item in metadata.items():
        path = _annotation_file(item["opp_policy_uid"])
        rows = []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for raw in csv.reader(handle):
                if len(raw) < 7:
                    continue
                try:
                    attributes = json.loads(raw[6])
                except json.JSONDecodeError:
                    attributes = {}
                texts = _selected_texts(attributes)
                selected = " ".join(dict.fromkeys(texts)).strip()
                if selected:
                    rows.append({"annotation_id": raw[0], "category": raw[5], "selected": selected})
        expected_rows = int(item["opp_annotation_rows"])
        if sum(1 for _ in csv.reader(path.open(encoding="utf-8-sig", newline=""))) != expected_rows:
            raise ValueError(f"Annotation row count no longer matches frozen metadata for {policy_id}")
        annotations[policy_id] = rows
        annotation_counts[policy_id] = expected_rows

    output_rows = []
    mapped_units = set()
    for unit in units:
        evidence = unit["exact_source_evidence"]
        evidence_norm = _normalise(evidence)
        evidence_tokens = _tokens(evidence)
        candidates = []
        for annotation in annotations[unit["policy_id"]]:
            selected = annotation["selected"]
            selected_norm = _normalise(selected)
            selected_tokens = _tokens(selected)
            if not selected_tokens or not evidence_tokens:
                continue
            intersection = len(evidence_tokens & selected_tokens)
            containment = intersection / min(len(evidence_tokens), len(selected_tokens))
            jaccard = intersection / len(evidence_tokens | selected_tokens)
            if selected_norm in evidence_norm or evidence_norm in selected_norm:
                method = "normalised_substring"
            elif intersection >= 4 and containment >= 0.60:
                method = "token_overlap_candidate"
            else:
                continue
            candidates.append((method, containment, jaccard, annotation))

        if not candidates:
            output_rows.append({
                "policy_id": unit["policy_id"], "unit_id": unit["unit_id"],
                "important_information": unit["important_information"], "opp_category": "",
                "annotation_id": "", "annotation_selected_text": "", "overlap_method": "unmapped",
                "token_containment": "", "token_jaccard": "",
                "review_decision": "", "review_notes": "",
            })
            continue
        mapped_units.add(unit["unit_id"])
        for method, containment, jaccard, annotation in sorted(
            candidates, key=lambda item: (item[3]["category"], -item[1], -item[2], item[3]["annotation_id"])
        ):
            output_rows.append({
                "policy_id": unit["policy_id"], "unit_id": unit["unit_id"],
                "important_information": unit["important_information"],
                "opp_category": annotation["category"], "annotation_id": annotation["annotation_id"],
                "annotation_selected_text": annotation["selected"], "overlap_method": method,
                "token_containment": f"{containment:.6f}", "token_jaccard": f"{jaccard:.6f}",
                "review_decision": "", "review_notes": "",
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(output_rows)
    audit = {
        "status": "candidate_mapping_requires_researcher_review",
        "source_unit_manifest_sha256": manifest["sha256"],
        "annotation_threshold": "0.75-overlap-similarity",
        "annotation_rows_by_policy": annotation_counts,
        "units": len(units), "mapped_candidate_units": len(mapped_units),
        "unmapped_candidate_units": len(units) - len(mapped_units),
        "candidate_rows": len(output_rows),
        "candidate_categories": dict(Counter(row["opp_category"] for row in output_rows if row["opp_category"])),
        "interpretation_warning": (
            "Automated overlap creates review candidates only. Unmapped does not by itself prove "
            "that a concept is absent from the OPP taxonomy."
        ),
    }
    write_json(AUDIT, audit)
    return audit


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
